import { authRequest } from "../store/auth-store";

export async function uploadMemberAvatar(memberId: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  await authRequest<void>(`/api/members/${memberId}/avatar`, {
    method: "PUT",
    body: form,
  });
}
