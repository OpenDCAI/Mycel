# Mycel Default Configurations

System default configurations for agents and model mappings.

## Directory Structure

```
defaults/
├── agents/
│   ├── default.json      # Base configuration with sensible defaults
│   ├── coder.json        # Optimized for code generation and analysis
│   ├── researcher.json   # Optimized for research and information gathering
│   └── tester.json       # Optimized for testing and QA
└── model_mapping.json    # Virtual model name mappings (leon:*)
```

## Agent Presets

### default.json
Base configuration with balanced settings suitable for general-purpose tasks.

- **Model**: claude-sonnet-4-5-20250929
- **Queue Mode**: steer (interrupts on new messages)
- **Context Limit**: 100K tokens
- **Use Case**: General assistant tasks, mixed workloads

### coder.json
Optimized for software development tasks requiring deep reasoning.

- **Model**: claude-opus-4-6 (most capable)
- **Temperature**: 0.0 (deterministic)
- **Queue Mode**: steer
- **Context Limit**: 200K tokens
- **Command Timeout**: 300s (for long builds/tests)
- **Memory**: Aggressive compaction (32K reserve, 40K recent)
- **Use Case**: Complex refactoring, architecture design, debugging

### researcher.json
Optimized for information gathering and analysis.

- **Model**: claude-sonnet-4-5-20250929 (cost-effective)
- **Temperature**: 0.3 (balanced)
- **Queue Mode**: collect (batches messages)
- **Context Limit**: 150K tokens
- **Web Search**: 10 results max, 30s timeout
- **File Size**: 20MB max (for large documents)
- **Commands**: Disabled (read-only)
- **Use Case**: Documentation research, competitive analysis, literature review

### tester.json
Optimized for test writing and validation.

- **Model**: claude-sonnet-4-5-20250929
- **Temperature**: 0.2 (slightly creative for edge cases)
- **Queue Mode**: followup (queues messages for after completion)
- **Context Limit**: 100K tokens
- **Network Commands**: Blocked (security)
- **Use Case**: Unit tests, integration tests, test coverage analysis

## Model Mappings

Virtual model names (`leon:*`) provide semantic aliases for common use cases:

| Virtual Name | Concrete Model | Temperature | Max Tokens | Use Case |
|--------------|----------------|-------------|------------|----------|
| `leon:fast` | sonnet-4-5 | 0.7 | 4K | Quick tasks, simple queries |
| `leon:balanced` | sonnet-4-5 | 0.5 | 8K | General use (default) |
| `leon:powerful` | opus-4-6 | 0.3 | 16K | Complex reasoning |
| `leon:coding` | opus-4-6 | 0.0 | 16K | Code generation |
| `leon:research` | sonnet-4-5 | 0.3 | 8K | Research tasks |
| `leon:creative` | sonnet-4-5 | 0.9 | 8K | Creative writing |

## Queue Modes

- **steer**: Interrupts agent immediately on new message (interactive)
- **followup**: Queues message for after current task completes (batch)
- **collect**: Buffers multiple messages, flushes on demand (research)
- **steer_backlog**: Adds to both steer and followup queues
- **interrupt**: Hard interrupt (reserved for critical events)

## Memory Configuration

### Pruning
Trims tool message content to manage context size:
- `soft_trim_chars`: Trim tool results longer than this
- `hard_clear_threshold`: Clear tool results longer than this
- `protect_recent`: Keep last N tool messages untrimmed

### Compaction
LLM-based summarization when context approaches limit:
- `reserve_tokens`: Reserve space for new messages
- `keep_recent_tokens`: Keep recent messages verbatim
- `summary_model`: Model for summarization (null = use main model)

## Usage

Load a preset via CLI:
```bash
mycel --agent coder
```

Or programmatically:
```python
from config.loader import load_config

config = load_config(agent="researcher")
```

## Customization

User configs override defaults via three-tier merge:
1. System defaults (this directory)
2. User global config (`~/.leon/config.json`)
3. Project config (`.leon/config.json`)

Example override:
```json
{
  "api": {
    "model": "leon:coding",
    "temperature": 0.1
  }
}
```
