/**
 * ManualStepCard - Renders individual remediation step with interactive actions.
 *
 * Extracted from RemediationModal.jsx (ARCHITECT-002)
 */
import { useToast } from "../Toast";
import {
  CheckCircleIcon,
  CopyIcon,
  RefreshIcon,
  NotepadIcon,
  ExternalLinkIcon,
} from "./icons";

export default function ManualStepCard({
  step,
  index,
  currentStep,
  completedSteps,
  generatedKey,
  generatingKey,
  openingFile,
  onSetCurrentStep,
  onGenerateKey,
  onCopyKey,
  onOpenInNotepad,
  onNavigate,
  onStepComplete,
  copied,
}) {
  const toast = useToast();

  return (
    <div
      className={`border rounded-lg transition-all ${
        index === currentStep
          ? "border-blue-500 bg-blue-900/20"
          : completedSteps.has(index)
          ? "border-green-600 bg-green-900/10"
          : "border-gray-700 bg-gray-800/50 opacity-60"
      }`}
    >
      <div
        className="p-4 cursor-pointer"
        role="button"
        tabIndex={0}
        onClick={() => onSetCurrentStep(index)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSetCurrentStep(index);
          }
        }}
      >
        <div className="flex items-start gap-3">
          <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
            completedSteps.has(index)
              ? "bg-green-600"
              : index === currentStep
              ? "bg-blue-600"
              : "bg-gray-700"
          }`}>
            {completedSteps.has(index) ? (
              <CheckCircleIcon />
            ) : (
              <span className="text-white font-semibold">{step.step}</span>
            )}
          </div>

          <div className="flex-1">
            <h3 className="font-semibold text-white">{step.title}</h3>
            <p className="text-gray-300 text-sm mt-1">{step.description}</p>

            {index === currentStep && (
              <div className="mt-4 space-y-4">
                {/* Generate key action */}
                {step.action === "generate_key" && (
                  <div className="space-y-3">
                    {generatedKey ? (
                      <div className="bg-gray-900 border border-gray-600 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-sm font-medium text-gray-300">Your New Key:</span>
                          <button
                            onClick={onCopyKey}
                            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                              copied
                                ? "bg-green-600 text-white"
                                : "bg-blue-600 hover:bg-blue-700 text-white"
                            }`}
                          >
                            <CopyIcon />
                            {copied ? "Copied!" : "Copy Key"}
                          </button>
                        </div>
                        <code className="block text-green-400 text-sm break-all font-mono bg-gray-950 p-3 rounded">
                          {generatedKey}
                        </code>
                      </div>
                    ) : (
                      <button
                        onClick={onGenerateKey}
                        disabled={generatingKey}
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
                      >
                        {generatingKey ? (
                          <>
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                            Generating...
                          </>
                        ) : (
                          <>
                            <RefreshIcon />
                            Generate Secure Key
                          </>
                        )}
                      </button>
                    )}
                  </div>
                )}

                {/* Navigate action */}
                {step.action === "navigate" && step.navigate_to && (
                  <button
                    onClick={() => onNavigate(step.navigate_to)}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
                  >
                    Go to {step.title}
                  </button>
                )}

                {/* File path with Open in Notepad button */}
                {step.file_path && (
                  <div className="bg-gray-900 border border-gray-600 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-sm text-gray-400">File: </span>
                        <code className="text-yellow-400 font-mono">{step.file_path}</code>
                      </div>
                      <button
                        onClick={onOpenInNotepad}
                        disabled={openingFile}
                        className="flex items-center gap-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
                      >
                        {openingFile ? (
                          <>
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                            Opening...
                          </>
                        ) : (
                          <>
                            <NotepadIcon />
                            Open in Notepad
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                )}

                {/* Code before/after */}
                {step.code_before && (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-red-400">Find this line:</p>
                    <pre className="bg-gray-950 border-2 border-red-800 rounded-lg p-3 text-sm overflow-x-auto">
                      <code className="text-red-300">{step.code_before}</code>
                    </pre>
                  </div>
                )}
                {step.code_after && (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-green-400">Replace with:</p>
                    <div className="relative">
                      <pre className="bg-gray-950 border-2 border-green-800 rounded-lg p-3 text-sm overflow-x-auto">
                        <code className="text-green-300">
                          {generatedKey
                            ? step.code_after.replace("<your-generated-key>", generatedKey)
                            : step.code_after}
                        </code>
                      </pre>
                      {generatedKey && (
                        <button
                          onClick={() => {
                            const text = step.code_after.replace("<your-generated-key>", generatedKey);
                            navigator.clipboard.writeText(text);
                            toast.success("Line copied!");
                          }}
                          className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-sm transition-colors"
                        >
                          <CopyIcon />
                          Copy
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Code snippet */}
                {step.code_snippet && (
                  <div className="relative">
                    <pre className="bg-gray-950 border border-gray-600 rounded p-3 text-sm overflow-x-auto">
                      <code className="text-gray-300">{step.code_snippet}</code>
                    </pre>
                    <button
                      aria-label="Copy code snippet"
                      onClick={() => {
                        navigator.clipboard.writeText(step.code_snippet);
                        toast.success("Code copied!");
                      }}
                      className="absolute top-2 right-2 p-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                    >
                      <CopyIcon />
                    </button>
                  </div>
                )}

                {/* Command */}
                {step.command && (
                  <div className="bg-gray-950 border border-gray-600 rounded-lg p-3 flex items-center justify-between">
                    <code className="text-cyan-400 font-mono text-sm">{step.command}</code>
                    <button
                      aria-label="Copy command"
                      onClick={() => {
                        navigator.clipboard.writeText(step.command);
                        toast.success("Command copied!");
                      }}
                      className="p-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                    >
                      <CopyIcon />
                    </button>
                  </div>
                )}

                {/* Docs link */}
                {step.docs_url && (
                  <a
                    href={step.docs_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-blue-400 hover:text-blue-300 text-sm transition-colors"
                  >
                    View Documentation
                    <ExternalLinkIcon />
                  </a>
                )}

                {/* Mark complete button */}
                {!completedSteps.has(index) && (
                  <button
                    onClick={() => onStepComplete(index)}
                    className="mt-4 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                  >
                    <CheckCircleIcon />
                    Mark as Complete
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
