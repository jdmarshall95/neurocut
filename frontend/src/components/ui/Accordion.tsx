import { Disclosure, DisclosureButton, DisclosurePanel } from "@headlessui/react";
import { ChevronDownIcon } from "@heroicons/react/24/outline";
import type { ReactNode } from "react";
import clsx from "clsx";

interface AccordionProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
}

export function Accordion({ title, children, defaultOpen, badge }: AccordionProps) {
  return (
    <Disclosure defaultOpen={defaultOpen}>
      {({ open }) => (
        <div className="glass-soft overflow-hidden rounded-2xl">
          <DisclosureButton className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-white/5">
            <span className="flex items-center gap-2.5 font-semibold text-slate-100">
              {title}
              {badge}
            </span>
            <ChevronDownIcon
              className={clsx(
                "h-5 w-5 shrink-0 text-slate-400 transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </DisclosureButton>
          <DisclosurePanel className="border-t border-white/5 px-5 py-4">
            {children}
          </DisclosurePanel>
        </div>
      )}
    </Disclosure>
  );
}
