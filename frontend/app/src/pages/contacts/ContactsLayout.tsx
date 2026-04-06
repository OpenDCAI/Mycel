import { Outlet } from "react-router-dom";

export default function ContactsLayout() {
  return (
    <div className="h-full w-full flex overflow-hidden">
      <div className="flex-1 min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
