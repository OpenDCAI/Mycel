import React from "react";
import { Link } from "react-router-dom";

export default function Breadcrumb({ items }: { items: Array<{ label: string; url: string }> }) {
  return (
    <div className="breadcrumb">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span> / </span>}
          <Link to={item.url}>{item.label}</Link>
        </React.Fragment>
      ))}
    </div>
  );
}
