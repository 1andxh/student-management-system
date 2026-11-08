import {
  SelectionIndicator,
  Tab as AriaTab,
  TabList as AriaTabList,
  TabPanel as AriaTabPanel,
  Tabs as AriaTabs,
  type TabListProps,
  type TabPanelProps,
  type TabProps,
  type TabsProps,
} from "react-aria-components";

// Segmented tabs: a recessed well with one raised pill that slides to the
// selected tab. React Aria's SelectionIndicator does the slide (it moves a
// single element between tabs, FLIP-style) — the same "one indicator
// following the selection" pattern as the styleguide theme switch, without
// measuring anything ourselves. Real tab semantics: arrow keys move between
// tabs, each tab controls its panel.

export function Tabs(props: Omit<TabsProps, "className" | "style"> & { className?: string }) {
  return <AriaTabs {...props} className={`flex flex-col gap-5 ${props.className ?? ""}`} />;
}

export function TabList<T extends object>(props: Omit<TabListProps<T>, "className" | "style">) {
  return (
    <AriaTabList
      {...props}
      className="grid auto-cols-fr grid-flow-col rounded-control bg-well p-1 shadow-[inset_0_1px_2px_var(--shade-2)]"
    />
  );
}

export function Tab({ children, ...props }: Omit<TabProps, "className" | "style" | "children"> & { children: React.ReactNode }) {
  return (
    <AriaTab
      {...props}
      className="relative flex h-8 cursor-default select-none items-center justify-center rounded-md px-3 text-small font-medium text-ink-2 outline-none transition-colors duration-150 ease-soft data-hovered:text-ink data-selected:text-ink data-focus-visible:outline-2 data-focus-visible:outline-offset-2 data-focus-visible:outline-accent pointer-coarse:h-11"
    >
      <SelectionIndicator className="absolute inset-0 rounded-md bg-surface shadow-control transition-[translate,width] duration-250 ease-snap" />
      <span className="relative">{children}</span>
    </AriaTab>
  );
}

export function TabPanel(props: Omit<TabPanelProps, "className" | "style">) {
  return <AriaTabPanel {...props} className="outline-none" />;
}
