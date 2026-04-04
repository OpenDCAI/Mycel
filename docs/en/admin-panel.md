# Mycel Admin Panel

中文 | [English](../en/admin-panel.md)

Mycel Admin is a standalone internal management panel for managing members and invite codes on the Mycel platform.

> **Security Warning**: The backend uses the Supabase service-role key to directly access the database. **Never expose this to the public internet.** Access only via SSH tunnel or internal network.

---

## Architecture

```
mycel-admin/
├── backend/          # FastAPI backend (Python)
│   ├── main.py       # All API routes
│   └── .env          # Environment variables (not committed)
└── src/              # React frontend (TypeScript + Vite)
    ├── api/client.ts # HTTP client (wraps fetch)
    ├── store/        # Zustand state (workspace switching)
    └── pages/        # Page components
```

**Port conventions**

| Service | Port |
|---------|------|
| Frontend (Vite dev) | 3100 |
| Backend (FastAPI) | 3101 |

---

## Workspace Concept

The backend maintains two Supabase clients mapped to different schemas:

| Workspace | Schema |
|-----------|--------|
| `production` | `public` |
| `staging` | `staging` |

Each API request specifies the target environment via the `X-Workspace` header. When the frontend switches workspaces, all pages automatically re-fetch their data.

---

## Getting Started

### Prerequisites

- Node.js + npm (frontend)
- Python 3.11+ + `uv` (backend)

### Backend

```bash
cd mycel-admin/backend

# Create .env
cat > .env << EOF
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
EOF

# Install dependencies and start
uv run uvicorn main:app --port 3101 --reload
```

### Frontend

```bash
cd mycel-admin
npm install
npm run dev  # Visit http://localhost:3100
```

---

## API Reference

All endpoints use the `X-Workspace: production | staging` header to target the correct environment.

### Invite Codes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/invite-codes` | List all invite codes (newest first) |
| POST | `/invite-codes` | Create invite code (`code` and `expires_days` are optional) |
| DELETE | `/invite-codes/{code}` | Revoke an invite code |

Code status is computed server-side: `available` / `used` / `expired`.

### Members

| Method | Path | Description |
|--------|------|-------------|
| GET | `/members` | List all members |
| PUT | `/members/{id}` | Update member (`name` and `is_admin` fields are optional) |
| DELETE | `/members/{id}` | Remove a member |

---

## Features

- **Member management**: View member list, toggle admin privileges, remove members
- **Invite code management**: View status (available/used/expired), generate new codes, revoke existing ones
- **Workspace switching**: A yellow warning banner appears at the top when staging is active to prevent accidental production changes

---

## Security Notes

- The backend uses username/password authentication with HMAC-SHA256 self-signed tokens
- `SUPABASE_SERVICE_ROLE_KEY` bypasses all RLS policies and directly accesses the database
- Production deployment: `https://admin.mycel.nextmind.space` (via FRP + nginx reverse proxy, HTTPS terminated at aliyun)
