import type { ToolStep } from "../../api";
import type { ToolRendererProps } from "./types";
import DefaultRenderer from "./DefaultRenderer";
import EditFileRenderer from "./EditFileRenderer";
import ListDirRenderer from "./ListDirRenderer";
import ReadFileRenderer from "./ReadFileRenderer";
import RunCommandRenderer from "./RunCommandRenderer";
import SearchRenderer from "./SearchRenderer";
import TaskRenderer from "./TaskRenderer";
import WebRenderer from "./WebRenderer";
import WriteFileRenderer from "./WriteFileRenderer";

type RendererComponent = React.ComponentType<ToolRendererProps>;

const TOOL_RENDERERS: Record<string, RendererComponent> = {
  // File edit
  Edit: EditFileRenderer,
  edit_file: EditFileRenderer,

  // File write
  Write: WriteFileRenderer,
  write_file: WriteFileRenderer,

  // Commands
  Bash: RunCommandRenderer,
  run_command: RunCommandRenderer,
  execute_command: RunCommandRenderer,

  // Read
  Read: ReadFileRenderer,
  read_file: ReadFileRenderer,

  // Directory listing
  ListDir: ListDirRenderer,
  list_directory: ListDirRenderer,
  list_dir: ListDirRenderer,

  // Search
  Grep: SearchRenderer,
  Glob: SearchRenderer,
  search: SearchRenderer,
  find_files: SearchRenderer,

  // Web
  WebFetch: WebRenderer,
  web_search: WebRenderer,
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
