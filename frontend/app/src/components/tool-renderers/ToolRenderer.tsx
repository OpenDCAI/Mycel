import BashRenderer from "./BashRenderer";
import DefaultRenderer from "./DefaultRenderer";
import EditFileRenderer from "./EditFileRenderer";
import ListDirRenderer from "./ListDirRenderer";
import ReadFileRenderer from "./ReadFileRenderer";
import SearchRenderer from "./SearchRenderer";
import TaskRenderer from "./TaskRenderer";
import WebRenderer from "./WebRenderer";
import WriteFileRenderer from "./WriteFileRenderer";
import type { ToolRendererProps } from "./types";

export function ToolRenderer(props: ToolRendererProps) {
  switch (props.step.name) {
    case "Edit":
      return <EditFileRenderer {...props} />;
    case "Write":
      return <WriteFileRenderer {...props} />;
    case "Bash":
      return <BashRenderer {...props} />;
    case "Read":
      return <ReadFileRenderer {...props} />;
    case "ListDir":
    case "list_dir":
      return <ListDirRenderer {...props} />;
    case "Grep":
    case "Glob":
      return <SearchRenderer {...props} />;
    case "WebFetch":
    case "WebSearch":
      return <WebRenderer {...props} />;
    case "Task":
    case "TaskCreate":
    case "TaskUpdate":
    case "TaskList":
    case "TaskGet":
      return <TaskRenderer {...props} />;
    default:
      return <DefaultRenderer {...props} />;
  }
}
