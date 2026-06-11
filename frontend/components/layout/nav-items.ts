import {
  Activity,
  BarChart3,
  Camera,
  FileSpreadsheet,
  Image as ImageIcon,
  LayoutDashboard,
  LucideIcon,
  MonitorPlay,
  Settings,
  UserCircle2,
  UserSearch,
  Users,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  comingSoon?: boolean;
}

// Labels reframed from "office attendance" to generic "people tracking".
// The underlying schema, routes, and APIs are unchanged — this is purely
// the operator-facing terminology. URLs (`/employees`, `/attendance`) are
// preserved so bookmarks and external links continue to work.
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Live View", href: "/live", icon: MonitorPlay },
  { label: "People Now", href: "/presence", icon: Activity },
  { label: "Registered People", href: "/employees", icon: Users },
  { label: "Unknown Faces", href: "/unknowns", icon: UserSearch },
  { label: "Face Training", href: "/training", icon: UserCircle2 },
  { label: "Cameras", href: "/cameras", icon: Camera },
  { label: "Activity Log", href: "/attendance", icon: BarChart3 },
  { label: "Event Photos", href: "/snapshots", icon: ImageIcon },
  { label: "Reports", href: "/reports", icon: FileSpreadsheet },
  { label: "Settings", href: "/settings", icon: Settings },
];
