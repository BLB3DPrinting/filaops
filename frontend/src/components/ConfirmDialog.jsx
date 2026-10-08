/**
 * ConfirmDialog - Accessible confirmation dialog to replace browser confirm()
 *
 * Usage:
 * const [showConfirm, setShowConfirm] = useState(false);
 * const [itemToDelete, setItemToDelete] = useState(null);
 *
 * <ConfirmDialog
 *   isOpen={showConfirm}
 *   title="Delete Item"
 *   message="Are you sure you want to delete this item?"
 *   confirmLabel="Delete"
 *   confirmVariant="danger"
 *   onConfirm={() => { deleteItem(itemToDelete); setShowConfirm(false); }}
 *   onCancel={() => setShowConfirm(false)}
 * />
 */
import { useEffect, useRef } from 'react';

const VARIANTS = {
  danger: {
    button: 'bg-status-red hover:brightness-90 text-paper font-semibold',
    icon: (
      <svg className="w-6 h-6 text-status-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  warning: {
    button: 'bg-status-amber hover:brightness-90 text-paper font-semibold',
    icon: (
      <svg className="w-6 h-6 text-status-amber" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  info: {
    button: 'bg-accent hover:bg-accent-press text-accent-ink font-semibold',
    icon: (
      <svg className="w-6 h-6 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
};

export default function ConfirmDialog({
  isOpen,
  title = 'Confirm',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'danger',
  onConfirm,
  onCancel,
  isLoading = false,
}) {
  const cancelButtonRef = useRef(null);
  const dialogRef = useRef(null);

  // Focus the cancel button when dialog opens (safer default for destructive actions)
  useEffect(() => {
    if (isOpen && cancelButtonRef.current) {
      cancelButtonRef.current.focus();
    }
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen && !isLoading) {
        onCancel();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, onCancel]);

  // Trap focus within dialog
  useEffect(() => {
    if (!isOpen) return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusableElements = dialog.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    const handleTabKey = (e) => {
      if (e.key !== 'Tab') return;

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

    dialog.addEventListener('keydown', handleTabKey);
    return () => dialog.removeEventListener('keydown', handleTabKey);
  }, [isOpen]);

  if (!isOpen) return null;

  const variant = VARIANTS[confirmVariant] || VARIANTS.danger;

  return (
    <div
      className="fixed inset-0 bg-[var(--glass-scrim)] flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) {
          onCancel();
        }
      }}
    >
      <div
        ref={dialogRef}
        className="bg-paper border border-hair rounded-xl w-full max-w-md p-6 shadow-[var(--shadow-pop)]"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
      >
        <div className="flex items-start gap-4">
          <div className="shrink-0 p-2 bg-paper-sunk rounded-full">
            {variant.icon}
          </div>
          <div className="flex-1">
            <h2
              id="confirm-dialog-title"
              className="text-lg font-semibold text-ink"
            >
              {title}
            </h2>
            <p
              id="confirm-dialog-message"
              className="mt-2 text-ink-3"
            >
              {message}
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="h-10 px-4 text-ink-2 hover:text-ink hover:bg-paper-sunk rounded-lg font-medium transition-colors disabled:text-ink-4"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`h-10 px-4 rounded-lg font-medium transition-colors disabled:bg-paper-sunk disabled:text-ink-4 ${variant.button}`}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Processing...
              </span>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
