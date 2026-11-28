import React from "react";
import { isStaleBuildError, reloadForNewBuild } from "../lib/staleBuild";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null, key: 0, reloading: false };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    // A screen's script file is gone because the app was updated while this
    // tab was open: reload once onto the new build instead of showing an error.
    if (isStaleBuildError(error) && reloadForNewBuild()) {
      this.setState({ reloading: true });
      return;
    }
    this.setState({ info });
    // why: place to send to Sentry/etc
    if (this.props.onError) this.props.onError(error, info);
     
    console.error("ErrorBoundary", error, info);
  }
  handleRetry = () =>
    this.setState({ error: null, info: null, key: this.state.key + 1 });

  render() {
    if (this.state.reloading) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-950">
          <div className="text-gray-300 text-sm">FilaOps was updated. Loading the new version…</div>
        </div>
      );
    }
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-950">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-w-lg w-full">
            <div className="text-red-300 font-semibold mb-2">Something broke</div>
            <div className="text-gray-300 text-sm mb-4">
              The UI hit an unexpected error. You can try again.
            </div>
            <div className="flex gap-2">
              <button
                onClick={this.handleRetry}
                className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm"
              >
                Retry
              </button>
              <button
                onClick={() => {
                  const msg = `${this.state.error?.stack || this.state.error?.message || String(this.state.error)}\n\n${
                    this.state.info?.componentStack || ""
                  }`;
                  navigator.clipboard?.writeText(msg).catch(() => {});
                }}
                className="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg text-sm border border-gray-700"
              >
                Copy details
              </button>
            </div>
            <pre className="text-xs text-gray-500 mt-4 max-h-48 overflow-auto whitespace-pre-wrap">
              {this.state.error?.message}
            </pre>
          </div>
        </div>
      );
    }
    return (
      <React.Fragment key={this.state.key}>{this.props.children}</React.Fragment>
    );
  }
}

