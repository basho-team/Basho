"use client";
import type { ReactNode, SelectHTMLAttributes } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowUpRight, Search, Inbox } from "lucide-react";
import Link from "next/link";
export function Intro({
  eyebrow = "ESPAÇO DE TRABALHO",
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="mb-2 text-[10px] font-bold tracking-[.18em] text-emerald-700">
          {eyebrow}
        </p>
        <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
          {title}
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          {description}
        </p>
      </div>
      {children}
    </div>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="grid gap-2 text-sm font-medium">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function NativeSelect({
  children,
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`field ${className}`} {...props}>
      {children}
    </select>
  );
}
export function Modal({
  title,
  description = "Operação no ambiente de demonstração. Nenhum serviço externo será acessado.",
  open,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
export function SearchBox({
  value,
  onChange,
  placeholder = "Pesquisar…",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative min-w-48 flex-1">
      <Search
        aria-hidden
        className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
      />
      <Input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pl-9"
      />
    </div>
  );
}
export function Empty({
  text = "Nenhum registro encontrado.",
}: {
  text?: string;
}) {
  return (
    <div className="grid justify-items-center gap-3 py-12 text-sm text-muted-foreground">
      <Inbox className="h-8 w-8" />
      {text}
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-emerald-900/10 bg-emerald-50/70 p-4 text-sm leading-relaxed text-emerald-950">
      {children}
    </div>
  );
}
export function GoLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <Link
      className="inline-flex items-center gap-2 text-sm font-medium text-emerald-800 hover:underline"
      href={href}
    >
      {children}
      <ArrowUpRight className="h-3.5 w-3.5" />
    </Link>
  );
}
export function Submit({
  children = "Salvar alterações",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="flex justify-end border-t pt-4">
      <Button type="submit">{children}</Button>
    </div>
  );
}
