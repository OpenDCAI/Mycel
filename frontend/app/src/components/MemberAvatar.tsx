/**
 * MemberAvatar — unified avatar component for all DOM surfaces.
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
  memberId: string;
  name: string;
  /** Member type — uses type-based color (consistent with network view). Falls back to ID hash. */
  type?: string;
  size?: keyof typeof SIZE_MAP;
  className?: string;
  /** Cache-bust revision — increment to force reload after upload */
  rev?: number;
}

export default function MemberAvatar({
  memberId,
  name,
  type,
  size = "md",
  className,
  rev,
}: MemberAvatarProps) {
  const sizeClass = SIZE_MAP[size];
  const fallbackColor = type ? colorForType(type).tw : colorForId(memberId);
  const src = `/api/members/${memberId}/avatar${rev ? `?v=${rev}` : ""}`;

  return (
    <Avatar className={cn(sizeClass, "shrink-0", className)}>
      <AvatarImage src={src} alt={name} />
      <AvatarFallback className={cn("font-semibold", fallbackColor)}>
        {getInitials(name)}
      </AvatarFallback>
    </Avatar>
  );
}
