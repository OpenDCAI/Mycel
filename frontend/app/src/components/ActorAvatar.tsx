/**
 * @@@universal-avatar — THE single avatar component. Used everywhere.
 * Displays avatar image from backend-provided URL with initials and placeholder color.
 * Backend decides the URL (human → account avatar, agent → user avatar).
 * Frontend just renders what backend gives.
 */

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { colorForType, colorForId, getInitials } from "@/lib/actor-colors";
import { cn } from "@/lib/utils";

const SIZE_MAP = {
  xs: "w-6 h-6 text-3xs",
  sm: "w-7 h-7 text-2xs",
  md: "w-10 h-10 text-xs",
  lg: "w-16 h-16 text-lg",
} as const;

interface ActorAvatarProps {
  name: string;
  /** Avatar image URL from backend. Frontend doesn't build URLs. */
  avatarUrl?: string;
  /** Actor type for deterministic placeholder color. */
  type?: string;
  size?: keyof typeof SIZE_MAP;
  className?: string;
  /** Cache-bust revision — increment to force reload after upload */
  rev?: number;
}

export default function ActorAvatar({
  name,
  avatarUrl,
  type,
  size = "md",
  className,
  rev,
}: ActorAvatarProps) {
  const sizeClass = SIZE_MAP[size];
  const placeholderColor = type ? colorForType(type).tw : colorForId(name);
  const src = avatarUrl ? `${avatarUrl}${rev ? `?v=${rev}` : ""}` : undefined;

  return (
    <Avatar className={cn(sizeClass, "shrink-0", className)}>
      {src && <AvatarImage src={src} alt={name} />}
      <AvatarFallback className={cn("font-semibold", placeholderColor)}>
        {getInitials(name)}
      </AvatarFallback>
    </Avatar>
  );
}
