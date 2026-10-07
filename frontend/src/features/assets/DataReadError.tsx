import { AlertTriangle, RotateCw } from "lucide-react";
import "./DataManagement.css";

type Props = { title: string; message: string; onRetry: () => void; retryLabel?: string };
export function DataReadError({ title, message, onRetry, retryLabel = "重新读取" }: Props) {
  return <div className="data-read-error" role="alert">
    <AlertTriangle size={20} aria-hidden="true" />
    <div className="data-read-error-copy"><strong>{title}</strong><p>{message}</p></div>
    <button type="button" className="btn btn-secondary" onClick={onRetry}><RotateCw size={15} aria-hidden="true" />{retryLabel}</button>
  </div>;
}
