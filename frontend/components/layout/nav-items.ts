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

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Live Presence", href: "/presence", icon: Activity },
  { label: "Employees", href: "/employees", icon: Users },
  { label: "Unknown Faces", href: "/unknowns", icon: UserSearch },
  { label: "Face Training", href: "/training", icon: UserCircle2 },
  { label: "Cameras", href: "/cameras", icon: Camera },
  { label: "Live View", href: "/live", icon: MonitorPlay },
  { label: "Attendance", href: "/attendance", icon: BarChart3 },
  { label: "Snapshots", href: "/snapshots", icon: ImageIcon },
  { label: "Reports", href: "/reports", icon: FileSpreadsheet },
  { label: "Settings", href: "/settings", icon: Settings },
];
