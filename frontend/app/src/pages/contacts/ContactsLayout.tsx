import { useParams } from "react-router-dom";
import SplitPaneLayout from "@/components/SplitPaneLayout";
import ContactList from "./ContactList";

export default function ContactsLayout() {
  const { id, userId } = useParams();

  return (
    <SplitPaneLayout
      sidebar={<ContactList />}
      hasDetail={Boolean(id || userId)}
    />
  );
}
