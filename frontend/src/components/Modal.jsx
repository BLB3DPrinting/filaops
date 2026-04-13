/**
 * Modal - Accessible modal wrapper component
 *
 * Provides: role="dialog", aria-modal, aria-labelledby, Escape key handling,
 * focus trapping, and backdrop click-to-close.
 *
 * Usage:
 *   <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Edit Item">
 *     <div className="p-6">... modal content ...</div>
 *   </Modal>
 */
import { useEffect, useRef, useId } from "react";

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  className = "w-full max-w-lg",
  disableClose = false,
}) {
  const dialogRef = useRef(null);
  const previousFocusRef = useRef(null);
  const titleId = useId();
  // Track where mousedown started so text-selection drags that end on the
  // backdrop don't accidentally close the modal.
  const pointerDownOnBackdropRef = useRef(false);

  // Save and restore focus when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement;
      // Focus the dialog container so screen readers announce it
      requestAnimationFrame(() => {
        if (dialogRef.current) {
          const firstFocusable = dialogRef.current.querySelector(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          );
          if (firstFocusable) {
            firstFocusable.focus();
          } else {
            dialogRef.current.focus();
          }
        }
      });
    } else if (previousFocusRef.current) {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen]);

  // Handle Escape key
  useEffect(() => {
    if (!isOpen || disableClose) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, disableClose, onClose]);

  // Focus trap
  useEffect(() => {
    if (!isOpen) return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleTabKey = (e) => {
      if (e.key !== "Tab") return;

      const focusableElements = dialog.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusableElements.length === 0) return;

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    dialog.addEventListener("keydown", handleTabKey);
    return () => dialog.removeEventListener("keydown", handleTabKey);
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onPointerDown={(e) => {
        pointerDownOnBackdropRef.current = e.target === e.currentTarget;
      }}
      onPointerUp={(e) => {
        if (pointerDownOnBackdropRef.current && e.target === e.currentTarget && !disableClose) {
          onClose();
        }
        pointerDownOnBackdropRef.current = false;
      }}
    >
      <div
        ref={dialogRef}
        className={`bg-gray-900 border border-gray-700 rounded-xl shadow-xl ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
      >
        {title && (
          <span id={titleId} className="sr-only">
            {title}
          </span>
        )}
        {children}
      </div>
    </div>
  );
}
