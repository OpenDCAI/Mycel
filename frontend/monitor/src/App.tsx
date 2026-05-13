import { BrowserRouter } from "react-router-dom";

import { MonitorRoutes } from "./app/routes";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <MonitorRoutes />
    </BrowserRouter>
  );
}
