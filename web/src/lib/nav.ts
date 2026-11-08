import type { Role } from "./api";

export type Area = "admin" | "teacher" | "student";

export interface NavItem {
  /** URL segment under the area; null for the area's home (index route). */
  slug: string | null;
  label: string;
  /** One line on what the page is for; shown in its header. */
  description: string;
  /** Planned stage, while the page is a placeholder. */
  stage?: string;
  /** Narrower than the area's roles (e.g. audit log: super admins only). */
  roles?: Role[];
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

// One sidebar per role, built around what that role actually does (the
// "role-specific homes" decision, ADR 0028 / plan F3) rather than one list
// of every resource. Pages from later stages are listed now, as honest
// placeholders, so the navigation can be judged as a whole.
export const NAV: Record<Area, NavGroup[]> = {
  admin: [
    { items: [{ slug: null, label: "Overview", description: "Your setup checklist, and anything that needs attention." }] },
    {
      label: "People",
      items: [
        { slug: "students", label: "Students", description: "Enrol students, issue PINs, assign sections.", stage: "F6b" },
        { slug: "teachers", label: "Teachers", description: "Teacher records and sign-in passwords.", stage: "F6b" },
        { slug: "users", label: "User accounts", description: "Staff accounts and roles.", stage: "F6b" },
        { slug: "change-requests", label: "Change requests", description: "Teachers’ requested changes to their details.", stage: "F6b" },
      ],
    },
    {
      label: "School structure",
      items: [
        { slug: "years", label: "Years & terms", description: "Academic years and their terms.", stage: "F6c" },
        { slug: "sections", label: "Grades & sections", description: "Grade levels, sections and who’s in them.", stage: "F6c" },
        { slug: "classes", label: "Subjects & classes", description: "What’s taught, by whom, and where.", stage: "F6c" },
      ],
    },
    {
      label: "Schedule",
      items: [{ slug: "timetable", label: "Timetable", description: "Bell schedule and each section’s week.", stage: "F6d" }],
    },
    {
      label: "Oversight",
      items: [{ slug: "audit", label: "Audit log", description: "Who changed what, and when.", stage: "F7", roles: ["super_admin"] }],
    },
  ],
  teacher: [
    {
      items: [
        { slug: null, label: "Today", description: "What you’re teaching now and next." },
        { slug: "classes", label: "My classes", description: "Rosters, assessments and gradebooks.", stage: "F4" },
        { slug: "details", label: "My details", description: "Your record, and requests to change it.", stage: "F4" },
      ],
    },
  ],
  student: [
    {
      items: [
        { slug: null, label: "Today", description: "Your classes today." },
        { slug: "timetable", label: "Timetable", description: "Your section’s week.", stage: "F5" },
        { slug: "grades", label: "Grades", description: "Your marks, by class.", stage: "F5" },
        { slug: "classes", label: "My classes", description: "What you’re enrolled in.", stage: "F5" },
        { slug: "profile", label: "Profile", description: "Your details.", stage: "F5" },
      ],
    },
  ],
};

export function visibleGroups(area: Area, role: Role): NavGroup[] {
  return NAV[area]
    .map((group) => ({ ...group, items: group.items.filter((item) => !item.roles || item.roles.includes(role)) }))
    .filter((group) => group.items.length > 0);
}

export function findNavItem(area: Area, slug: string | null, role: Role): NavItem | undefined {
  return visibleGroups(area, role)
    .flatMap((group) => group.items)
    .find((item) => item.slug === slug);
}

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super admin",
  admin: "Admin",
  teacher: "Teacher",
  student: "Student",
};
