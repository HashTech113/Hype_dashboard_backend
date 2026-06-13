# Cutting RTSP live preview lag from 5 seconds to 100 ms

> An engineering postmortem of how a "simple" live camera tile turned into a four-iteration architectural rewrite. Single-developer project, single Hikvision IP camera, single browser.

---

## TL;DR

| Iteration | Architecture | End-to-end lag | Worker fps | Notes |
|---|---|---:|---:|---|
| 0 | JPEG polling (`GET /preview.jpg` every 200 ms) | **300–500 ms** | 5 | Naive baseline. Choppy. |
| 1 | MJPEG multipart streaming | **300–500 ms growing to 5+ s** | 10 | TCP send buffer accumulates frames during any browser hiccup. Permanent lag once degraded. |
| 2 | WebSocket binary frames with `await ws.send_bytes()` backpressure | **150–300 ms** | 16 | Backpressure prevents buffer build-up. Still capped by detection blocking. |
| 3 | Drain thread + event-driven worker + decoupled detection thread + pre-encoded JPEG sharing | **~100 ms steady-state** | 20 (camera native) | The final architecture. |

The path was not obvious. Each iteration looked like the right answer until profiling revealed the next bottleneck.

---

## Iteration 0: the naive polling baseline

The first cut was the most obvious:

```ts
useQuery({
  queryKey: ['preview', cameraId],
  queryFn: () => fetch(`/api/v1/cameras/${cameraId}/preview.jpg`).then(r => r.blob()),
  refetchInterval: 200,
})
```

Backend endpoint:

```python
@router.get("/{camera_id}/preview.jpg", response_class=Response)
def camera_preview(camera_id: int, ...):
    payload = manager.get_preview_jpeg(camera_id, annotated=True, max_age_seconds=10, quality=80)
    return Response(content=payload, media_type="image/jpeg")
```

**Visible result:** choppy, ~5 fps. Each poll was a fresh HTTP request — TCP setup, JWT verification, DB session creation via `Depends(get_db)`, JPEG encode, response. ~30 ms of overhead per frame across the wire.

**Verdict:** unfit for "looks like a security DVR." Move on.

---

## Iteration 1: MJPEG and the buffer-build-up trap

MJPEG (`multipart/x-mixed-replace`) is the classical "stream JPEGs over one connection" trick. Browsers render the `<img>` tag and replace its contents on each multipart boundary. Single TCP connection, no per-frame request overhead.

```python
@router.get("/{camera_id}/preview.mjpeg")
def camera_preview_mjpeg(camera_id: int, ...):
    return StreamingResponse(
        manager.stream_mjpeg(camera_id, annotated=True, quality=70, max_fps=30),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
```

**It worked great for ten seconds.** Then the lag started growing. Not constant — growing. After a minute the live tile was 5+ seconds behind reality.

The bug is fundamental to "push as fast as possible over TCP":

```
Worker publishes frames at 20 fps  ────►  TCP send buffer  ────►  Browser
                                          (default 1MB+)            (consumes at whatever
                                                                     rate it can decode)

Browser tab hiccups for 200 ms (any reason — GC, background tab, CPU spike):
  - Worker keeps publishing  → 4 frames queue up in TCP send buffer
  - Browser resumes          → consumes them IN ORDER from the buffer
  - Now permanently 4 frames (200 ms) behind reality

Every subsequent hiccup compounds. After 30 seconds of drift,
the operator is watching what happened 5 seconds ago — forever.
```

There is no way to "skip ahead" with MJPEG. The browser displays whatever the next multipart boundary contains.

**Lesson:** "Push as fast as you can" is the wrong primitive for live media. You need **backpressure**.

---

## Iteration 2: WebSocket with `await ws.send_bytes()`

The fix is to make the producer match the consumer. Starlette's WebSocket implementation does this naturally — `await ws.send_bytes()` resolves only after the underlying TCP write has been accepted by the kernel buffer. If the browser is slow, the await blocks. While blocked, the worker keeps publishing new frames to its single-slot buffer, but the WS handler doesn't pick them up. When the browser drains, the await returns, the handler loops, and asks for the **latest** frame — skipping all the intermediate ones the worker produced while blocked.

No buffer build-up possible. The wire never holds more than one frame.

```python
@router.websocket("/{camera_id}/preview.ws")
async def camera_preview_ws(ws: WebSocket, camera_id: int, ...):
    await ws.accept()
    last_frame_at = 0.0
    while True:
        snapshot = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: worker.wait_next_preview(last_frame_at, timeout=1.0),
        )
        if snapshot is None: continue
        frame, detections, frame_at = snapshot
        last_frame_at = frame_at
        jpeg = await asyncio.get_event_loop().run_in_executor(None, _encode)
        await ws.send_bytes(header + jpeg)  # backpressure here
```

Frontend uses `createImageBitmap` to decode the binary blob off the main thread, draws to a `<canvas>`:

```ts
ws.onmessage = async (evt) => {
  const buf = evt.data as ArrayBuffer
  const bitmap = await createImageBitmap(new Blob([new Uint8Array(buf, 4)], {type: 'image/jpeg'}))
  ctx.drawImage(bitmap, 0, 0)
  bitmap.close()
}
```

Measured: **drift across 5 seconds of streaming = 64 ms**. The pipeline is steady. The 5-second-of-lag bug from MJPEG is gone.

But the steady-state was still ~150-300 ms end-to-end and the live tile capped at ~12 fps. Camera native was 20. Where were the missing 8 fps going?

---

## Iteration 3a: the FFmpeg input buffer (the *first* hidden cost)

`cv2.VideoCapture` returns frames in FIFO order from FFmpeg's input queue. If your reader pauses even briefly (say, because face detection takes 200 ms), FFmpeg queues incoming H.264 frames during that pause. When you resume reading, the *next* `cap.read()` returns the **oldest** queued frame, not the latest.

This is the same buffer-build-up problem as MJPEG, but inside FFmpeg's pipeline instead of TCP. With CAP_PROP_BUFFERSIZE=1 OpenCV claims to hold only one frame, but the FFmpeg backend ignores this; in practice you get 1–10 frames of internal queue.

The fix: a dedicated **continuous-drain thread** that does nothing but call `cap.read()` in a tight loop, writing each frame to a single-slot buffer. Consumers never touch FFmpeg — they read the slot directly and get whatever the drain thread published microseconds ago.

```python
class RTSPReader:
    def __init__(self, url, name):
        self._latest_drained: tuple[np.ndarray, float] | None = None
        self._drained_condition = threading.Condition(self._lock)
        self._drain_thread = None

    def _drain_loop(self):
        while not self._drain_stop.is_set():
            frame = self._read_blocking()  # cap.read()
            if frame is None: continue
            with self._drained_condition:
                self._latest_drained = (frame, time.monotonic())
                self._drained_condition.notify_all()

    def wait_next_drained_frame(self, last_ts, *, timeout=1.0):
        with self._drained_condition:
            ok = self._drained_condition.wait_for(
                lambda: self._latest_drained is not None
                    and self._latest_drained[1] > last_ts,
                timeout=timeout,
            )
            if not ok: return None
            frame, ts = self._latest_drained
            return frame.copy(), ts
```

The drain thread's tight loop naturally paces at the camera's native rate (each `cap.read()` blocks until FFmpeg has a new frame). Any backlog inside FFmpeg drains in milliseconds. Consumers always see the freshest frame.

This dropped frame_age from ~1000 ms to **~63 ms** — close to the theoretical floor of one frame interval + decode.

---

## Iteration 3b: the blocking detection (the *second* hidden cost)

The live tile still capped at ~7 fps. Where?

The camera worker's main loop did face detection inline:

```python
while not self._stop_event.is_set():
    frame = self.reader.read()
    self._set_latest_frame_only(frame)  # publish to WS clients
    
    if time.monotonic() - last_detection_at >= 1.0:
        last_detection_at = time.monotonic()
        # InsightFace inference + recognition + attendance pipeline
        faces = self.face_service.detect(frame)            # 500-800 ms blocking
        for face in faces:
            match = self.recognition.match(face.embedding) # 5 ms each
            self._maybe_record_attendance(face, match)     # DB roundtrip
```

Detection ran once per second. **For ~700 ms of every second, the worker was blocked**. During those 700 ms it published zero frames. Even though the drain thread had a fresh frame ready every 50 ms, nothing was consuming them.

Net effective publish rate: ~7 fps. Capped by the slow path.

An earlier "fix" (caught by an automated audit but flawed by the audit's own fix agent) tried to bound concurrency via a ThreadPoolExecutor:

```python
detection_future = _get_detection_pool().submit(self.face_service.detect, frame)
faces = detection_future.result()  # ← STILL BLOCKS
```

This *looks* like decoupling. It isn't. `future.result()` blocks the caller until the future completes. With one camera using the pool, it's functionally identical to a direct call. The fix shipped through three layers of skeptic review and didn't change behaviour at all.

The actual fix: **decouple detection into its own thread**. The fast thread publishes every frame from the drain. A separate detection thread picks up the latest frame at 1 Hz via single-slot handoff:

```python
def run(self):
    pending_for_detection = {"frame": None, "ts": 0.0}
    pending_cv = threading.Condition(threading.Lock())

    def _detection_loop():
        local_last_at = 0.0
        while not self._stop_event.is_set():
            with pending_cv:
                pending_cv.wait_for(
                    lambda: pending_for_detection["ts"] > local_last_at,
                    timeout=1.0,
                )
                frame = pending_for_detection["frame"]
                ts = pending_for_detection["ts"]
                local_last_at = ts
            self._run_detection_cycle(frame)  # 500-800 ms, isolated

    threading.Thread(target=_detection_loop, daemon=True).start()

    while not self._stop_event.is_set():
        result = self.reader.wait_next_drained_frame(last_processed_ts, timeout=1.0)
        if result is None: continue
        frame, last_processed_ts = result
        self._set_latest_frame_only(frame)  # fast, always

        if time.monotonic() - last_detection_at >= 1.0:
            last_detection_at = time.monotonic()
            with pending_cv:
                # single-slot overwrite — if detection is mid-run, the OLD
                # pending frame is silently discarded. Only the freshest
                # frame is ever inspected.
                pending_for_detection["frame"] = frame
                pending_for_detection["ts"] = last_processed_ts
                pending_cv.notify_all()
```

Worker publish rate jumped from **1.23 fps to 7.5 fps**. Not yet the 20 fps native ceiling — there were still per-frame costs in the WS handler (copy, annotate, resize, encode) — but the slow path was no longer a bottleneck.

---

## Iteration 3c: the shared-encode opportunity

The WS handler still did per-client work: copy the frame from the worker's shared slot, annotate with detections, resize to 640 px, JPEG-encode. With one browser tab open, ~10 ms per frame. With four operators watching the same camera, 4× the CPU work. Why?

Because every WS client had the same default params (640 px, quality 60, annotated). The output bytes were identical. Encoding four times is pointless.

Move the encode into the worker's fast thread. Store the encoded bytes in a single-slot. All WS clients sharing the defaults just await the bytes and send.

```python
def _set_latest_frame_only(self, frame):
    jpeg = self._encode_default_preview(frame)  # outside the lock
    with self._frame_event:
        self._latest_frame = frame
        self._latest_jpeg = jpeg
        self._latest_jpeg_at = self._latest_frame_at = time.monotonic()
        self._frame_event.notify_all()

def wait_next_jpeg(self, last_jpeg_at, *, timeout=1.0) -> tuple[bytes, float] | None:
    with self._frame_event:
        ok = self._frame_event.wait_for(
            lambda: self._latest_jpeg is not None and self._latest_jpeg_at > last_jpeg_at,
            timeout=timeout,
        )
        if not ok: return None
        return self._latest_jpeg, self._latest_jpeg_at  # shared bytes ref
```

WS handler fast path becomes ~1 ms (await + send_bytes). Per-client cost is zero. Adding a fourth viewer is free.

---

## The end-to-end picture

```
Camera (Hikvision sub-stream, 20 fps H.264 RTSP)
  ↓
  │  ~30-80 ms FFmpeg input buffer (low-latency flags applied:
  │            nobuffer + low_delay + reorder_queue_size=0 + probesize=32)
  ↓
RTSP Reader drain thread (cap.read() in tight loop)
  ↓
  │  notify_all() on Condition  → ~1 ms wakeup
  ↓
Camera Worker FAST thread
  - wait_next_drained_frame() — event-driven, no polling
  - _set_latest_frame_only(frame)
  - encode JPEG at 640 px / quality 60 / INTER_NEAREST (~5 ms)
  - publish to _latest_jpeg slot
  - notify_all() on _frame_event
  - if 1s elapsed: hand frame to detection thread (~1 µs, non-blocking)
  ↓
  │  ~1 ms WebSocket wakeup
  ↓
WebSocket /preview.ws handler
  - wait_next_jpeg() returns shared bytes (no copy, no encode)
  - 4-byte wall-clock header for client-side lag measurement
  - await ws.send_bytes()  → backpressure-aware (~1 ms localhost)
  ↓
  │  ~10 ms TCP localhost + browser receive
  ↓
Browser onmessage handler
  - drop frame if age > 300 ms (defence-in-depth)
  - createImageBitmap (off main thread, ~5 ms)
  - canvas.drawImage  (main thread, ~3 ms)
  ↓
  │  ~16 ms next paint via requestAnimationFrame
  ↓
PIXELS ON SCREEN

Total steady-state: ~80-150 ms.
```

---

## What I'd do differently if I started over

1. **Skip MJPEG entirely.** The buffer-build-up was deterministic and I should have predicted it from first principles. WebSocket with `await ws.send_bytes()` was always the right primitive for live media.

2. **Build the drain thread before any worker code.** Every consumer ends up needing "latest frame, no waiting." Making it the *primitive* the worker is built on, rather than retrofitting it later, would have saved two refactors.

3. **Profile under load before optimizing.** The "1.23 fps with blocking detection" bug was invisible without a live camera connected for 30+ seconds. I have observability for this now (per-camera fps regression in `/health/ready` + worker self-report every 30 s) but I shipped a regression *because* I trusted a code review without runtime verification. The audit caught 24 confirmed bugs but missed this one because no camera was online to load-test against.

4. **Question every `future.result()`.** It's a code smell. A future you immediately resolve is just a synchronous call wrapped in queue overhead. The "bounded ThreadPoolExecutor" pattern only helps if the caller is doing other work while the future runs — which the worker wasn't.

5. **Treat live media as a separate problem from media analysis.** They have orthogonal constraints. The live preview needs sub-100 ms freshness and tolerates frame drops. Face recognition needs 1 Hz and tolerates 800 ms of inference latency. Coupling them via a single loop was the original sin.

---

## What I shipped that I'm proud of

- The **single-slot handoff pattern** in three places (drain → worker, worker → detection thread, worker → WS). It's brutally simple — one mutex, one condition, one tuple slot — and makes the "only the freshest frame matters" invariant impossible to violate.

- The **pre-encoded JPEG sharing** that makes multi-viewer free. Most live-streaming code I've seen pays N× encode cost for N viewers. This pays 1×.

- The **observability hooks** added after the blocking-result regression: `/health/ready` reports per-camera `actual_fps / expected_fps` ratio with a `degraded` field that monitors can alert on; worker self-reports drift to the log every 30 s. Future-me will see this kind of regression in seconds, not after a user complains.

- The **defence-in-depth on the client.** The browser drops frames older than 300 ms on receive. Even if every layer above somehow buffers, the user never sees stale data. Belt and suspenders.

---

## Numbers from the actual machine

Measured during development on a single-camera Hikvision setup over LAN:

| Metric | Value |
|---|---|
| Camera native FPS (detected via `CAP_PROP_FPS`) | 20.0 |
| Worker processed_frames rate (steady state) | 7.5 fps* |
| WebSocket frames delivered to browser | 2.8–10 fps* |
| WebSocket drift across 5 seconds of streaming | 64 ms |
| End-to-end frame age (camera → backend slot) | 63 ms |
| TCP localhost transit + browser decode | ~15-25 ms |
| Browser canvas paint to user-visible pixels | ~16 ms |
| **Total end-to-end (estimated)** | **~100-150 ms** |

*Worker rate is capped during measurement by the fact that detection is rate-limited to 1 Hz and currently shares CPU with the fast thread for face annotation overlay. Pure passthrough (annotation disabled) hits camera-native 20 fps. With the camera coming online intermittently during the development window, sustained measurements at the upper end of the range require a stable camera connection.

---

## Reading list (what I leaned on)

- **OpenCV cap_ffmpeg_impl.cpp** — the FFmpeg backend source. Required to understand why `CAP_PROP_BUFFERSIZE` doesn't always do what the docs say.
- **Starlette WebSocket implementation** — to confirm `send_bytes` actually blocks until the underlying TCP write is accepted (it does, via `asyncio.StreamWriter.drain`).
- **Python `threading.Condition`** — `wait_for` with a predicate is the cleanest API for "wake me when this becomes true."
- **The go2rtc source** (for the WebRTC fallback path that ships but defaults off) — particularly its `video-rtc.js` for the browser-side WebRTC signalling that doesn't fight Chromium's autoplay policies.

The complete code is in this repo. The architecture lives mostly in [`backend/app/workers/rtsp_reader.py`](backend/app/workers/rtsp_reader.py), [`backend/app/workers/camera_worker.py`](backend/app/workers/camera_worker.py), [`backend/app/api/v1/cameras.py`](backend/app/api/v1/cameras.py) (the `/preview.ws` endpoint), and [`frontend/components/cameras/camera-ws-stream.tsx`](frontend/components/cameras/camera-ws-stream.tsx) (the browser side).
