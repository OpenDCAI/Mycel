import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot } from "lucide-react";
import { useAppStore } from "@/store/app-store";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function CreateMemberDialog({ open, onOpenChange }: Props) {
  const navigate = useNavigate();
  const addMember = useAppStore(s => s.addMember);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleCreate = async () => {
    if (!name.trim()) return;
    try {
      const member = await addMember(name.trim(), description.trim());
      onOpenChange(false);
      setName("");
      setDescription("");
      navigate(`/contacts/agents/${member.id}`);
    } catch (e) {
      toast.error("创建失败，请重试");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Bot className="w-4.5 h-4.5 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">创建新成员</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">定义一名新的 AI 成员</DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="name" className="text-sm">名称 <span className="text-destructive">*</span></Label>
            <Input id="name" placeholder="例如: Code Reviewer" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-2">
            <Label htmlFor="desc" className="text-sm">描述 <span className="text-muted-foreground text-xs">（可选）</span></Label>
            <Textarea id="desc" placeholder="简要描述这名成员的职责..." value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleCreate} disabled={!name.trim()}>创建并配置</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
