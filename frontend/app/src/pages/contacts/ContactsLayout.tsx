import { Outlet, useParams } from "react-router-dom";
import { useIsMobile } from "@/hooks/use-mobile";
import ContactList from "./ContactList";

export default function ContactsLayout() {
  const isMobile = useIsMobile();
  const { id } = useParams();
  const hasDetail = Boolean(id);

  if (isMobile) {
    if (hasDetail) {
      return (
        <div className="h-full w-full">
          <Outlet />
        </div>
      );
    }
    return (
      <div className="h-full w-full">
        <ContactList />
      </div>
    );
  }

  return (
    <div className="h-full w-full flex overflow-hidden">
      <div className="w-72 shrink-0 h-full">
        <ContactList />
      </div>
      <div className="flex-1 min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
