export function BambuddyLegalNotice() {
  return (
    <section className="bg-gray-900/40 border border-gray-700/70 rounded-lg p-5">
      <h2 className="text-sm font-semibold text-gray-200">AGPL Service Notice</h2>
      <p className="text-sm text-gray-400 mt-2">
        Bambuddy runs as a separate AGPL service. FilaOps PRO communicates with it through HTTP APIs.
      </p>
      <a
        href="https://github.com/maziggy/bambuddy"
        target="_blank"
        rel="noreferrer"
        className="inline-flex mt-3 text-sm text-blue-400 hover:text-blue-300"
      >
        Bambuddy source and license
      </a>
    </section>
  );
}
