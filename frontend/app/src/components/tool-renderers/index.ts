import type { ToolStep } from "../../api";
import type { ToolRendererProps } from "./types";
import BashRenderer from "./BashRenderer";
import DefaultRenderer from "./DefaultRenderer";
import EditFileRenderer from "./EditFileRenderer";
import ListDirRenderer from "./ListDirRenderer";
import ReadFileRenderer from "./ReadFileRenderer";
import SearchRenderer from "./SearchRenderer";
import TaskRenderer from "./TaskRenderer";
import WebRenderer from "./WebRenderer";
import WriteFileRenderer from "./WriteFileRenderer";

type RendererComponent = React.ComponentType<ToolRendererProps>;

const TOOL_RENDERERS: Record<string, RendererComponent> = {
  // File edit
  Edit: EditFileRenderer,

  // File write
  Write: WriteFileRenderer,

  // Commands
  Bash: BashRenderer,

  // Read
  Read: ReadFileRenderer,

  // Directory listing
  ListDir: ListDirRenderer,
  list_dir: ListDirRenderer,

  // Search
  Grep: SearchRenderer,
  Glob: SearchRenderer,

  // Web
  WebFetch: WebRenderer,
  WebSearch: WebRenderer,

  // Task/agent delegation
  Task: TaskRenderer,
  TaskCreate: TaskRenderer,
  TaskUpdate: TaskRenderer,
  TaskList: TaskRenderer,
  TaskGet: TaskRenderer,
};

export function getToolRenderer(step: ToolStep): RendererComponent {
  return TOOL_RENDERERS[step.name] ?? DefaultRenderer;
}

export type { ToolRendererProps } from "./types";
