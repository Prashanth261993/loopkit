import { useEffect } from "react";

// Minimal, dependency-free image lightbox. Click the backdrop, the close
// button, or press Esc to dismiss. Body scroll is locked while open so the
// zoomed diagram stays put. Used by the architecture diagrams (real Excalidraw
// SVGs benefit from a full-size read), but generic over any {src, alt}.
export function Lightbox({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className="lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={alt}
      onClick={onClose}
    >
      <button className="lightbox-close" aria-label="Close" onClick={onClose}>
        ×
      </button>
      <figure className="lightbox-figure" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={alt} />
        <figcaption>{alt}</figcaption>
      </figure>
    </div>
  );
}
