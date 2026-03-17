/**
 * @@@universal-avatar — THE single avatar component. Used everywhere.
 * Shows avatar image from /api/members/{id}/avatar with initials fallback.
 * Radix Avatar handles the fallback automatically on 404 or load error.
 */

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { colorForType, colorForId, getInitials } from "@/lib/member-colors";
import { cn } from "@/lib/utils";

const SIZE_MAP = {
  xs: "w-6 h-6 text-[8px]",
  sm: "w-7 h-7 text-[10px]",
  md: "w-10 h-10 text-xs",
  lg: "w-16 h-16 text-lg",
} as const;

interface MemberAvatarProps {
  name: string;
  /** Member/entity ID — used for image URL + deterministic color hash. */
  id?: string;
  /** Member type — human | mycel_agent | openclaw_agent → type-based color. */
  type?: string;
  size?: keyof typeof SIZE_MAP;
  className?: string;
  /** Cache-bust revision — increment to force reload after upload */
  rev?: number;
}

export default function MemberAvatar({
  name,
  id,
  type,
  size = "md",
  className,
  rev,
}: MemberAvatarProps) {
  const sizeClass = SIZE_MAP[size];
  const fallbackColor = type ? colorForType(type).tw : id ? colorForId(id) : colorForId(name);
  const src = id ? `/api/members/${id}/avatar${rev ? `?v=${rev}` : ""}` : undefined;

  return (
    <Avatar className={cn(sizeClass, "shrink-0", className)}>
      {src && <AvatarImage src={src} alt={name} />}
      <AvatarFallback className={cn("font-semibold", fallbackColor)}>
        {getInitials(name)}
      </AvatarFallback>
    </Avatar>
  );
}
