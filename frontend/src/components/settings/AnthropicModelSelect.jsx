/**
 * AnthropicModelSelect - Claude model dropdown for the AI settings.
 *
 * The list comes from the backend (GET /settings/ai/anthropic-models), which
 * asks Anthropic which models the saved API key can use. Nothing here is
 * hard-coded, so the list stays current as Anthropic adds and retires models.
 *
 * The saved model always stays selectable. When Anthropic's list does not
 * include it, it is marked "not listed by Anthropic (may be retired)"; when
 * the list could not be loaded, the page says the model was not checked.
 */
import { useEffect, useState } from "react";
import { API_URL } from "../../config/api";

const DEFAULT_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing";

function optionLabel(model, recommended) {
  const name = model.display_name && model.display_name !== model.id
    ? `${model.display_name} (${model.id})`
    : model.id;
  const notes = [];
  if (model.id === recommended) notes.push("recommended");
  if (model.lifecycle === "deprecated") notes.push("deprecated, retiring soon");
  return notes.length ? `${name} - ${notes.join(", ")}` : name;
}

/** Fetch the model list. Resolves to the next component state; never throws. */
async function requestModels(refresh) {
  try {
    const query = refresh ? "?refresh=true" : "";
    const response = await fetch(`${API_URL}/api/v1/settings/ai/anthropic-models${query}`, {
      credentials: "include",
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Error ${response.status}`);
    }
    return { status: "ready", data: await response.json(), error: null };
  } catch (error) {
    return { status: "failed", data: null, error: error.message || "Request failed" };
  }
}

export default function AnthropicModelSelect({ value, savedModel, onChange, apiKeyMasked }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  // Load on mount and again when a different key is saved. A late answer for
  // an older key is dropped.
  useEffect(() => {
    let current = true;
    requestModels(false).then((next) => {
      if (current) setState(next);
    });
    return () => {
      current = false;
    };
  }, [apiKeyMasked]);

  const refreshModels = async () => {
    setState((prev) => ({ ...prev, status: "loading" }));
    setState(await requestModels(true));
  };

  const data = state.data;
  const models = data?.models || [];
  const listedIds = new Set(models.map((m) => m.id));
  const fromAnthropic = data?.source === "anthropic";
  const recommended = data?.recommended;
  const pricingUrl = data?.pricing_url || DEFAULT_PRICING_URL;

  // Keep the saved and the current value selectable even if no list has them.
  const extraIds = [...new Set([savedModel, value].filter((id) => id && !listedIds.has(id)))];
  const unlistedLabel = fromAnthropic
    ? "not listed by Anthropic (may be retired)"
    : "saved value, not checked with Anthropic";
  const valueIsUnlisted = Boolean(value) && !listedIds.has(value);

  return (
    <div>
      <label htmlFor="ai_anthropic_model" className="block text-sm font-medium text-gray-300 mb-1">
        Model
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <select
          id="ai_anthropic_model"
          name="ai_anthropic_model"
          value={value || ""}
          onChange={onChange}
          disabled={state.status === "loading" && !data}
          className="w-full md:w-auto md:min-w-[28rem] max-w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
        >
          {!value && <option value="">Select a model</option>}
          {extraIds.map((id) => (
            <option key={`unlisted-${id}`} value={id}>
              {`${id} - ${unlistedLabel}`}
            </option>
          ))}
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {optionLabel(model, recommended)}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={refreshModels}
          disabled={state.status === "loading"}
          className="text-sm text-blue-400 hover:underline disabled:text-gray-500"
        >
          {state.status === "loading" ? "Loading models..." : "Refresh list"}
        </button>
      </div>

      {state.status === "failed" && (
        <p role="alert" className="text-sm text-red-300 mt-1">
          Couldn&apos;t load the model list: {state.error}. The saved model is still selected;
          use Test Connection to check it.
        </p>
      )}
      {data && !fromAnthropic && data.error && (
        <p role="status" className="text-sm text-yellow-300 mt-1">
          Showing a built-in list of current models. {data.error}
        </p>
      )}
      {valueIsUnlisted && data && (
        <p role="alert" className="text-sm text-yellow-300 mt-1">
          {fromAnthropic
            ? `Anthropic does not list "${value}" for this API key. It may be retired or mistyped. Pick a listed model, then Test Connection.`
            : `"${value}" could not be checked with Anthropic. Use Test Connection before relying on it.`}
        </p>
      )}

      <p className="text-sm text-gray-400 mt-1">
        {recommended ? `Recommended for invoice parsing: ${recommended}. ` : ""}
        Cost depends on the model and the invoice size; see{" "}
        <a
          href={pricingUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:underline"
        >
          Anthropic&apos;s pricing
        </a>
        .
      </p>
    </div>
  );
}
