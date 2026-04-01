/**
 * AdminNotifications - Operator messaging / notification inbox
 *
 * Thread-based view: left panel lists threads, right panel shows messages + reply.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

function formatTimeAgo(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default function AdminNotifications() {
  const api = useApi();
  const toast = useToast();
  const navigate = useNavigate();
  const { isPro } = useFeatureFlags();

  const [threads, setThreads] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);

  // Compose new thread state
  const [showCompose, setShowCompose] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [composeRecipient, setComposeRecipient] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeSending, setComposeSending] = useState(false);
  const [customerSearch, setCustomerSearch] = useState("");

  useEffect(() => {
    fetchThreads();
  }, [unreadOnly]);

  const fetchThreads = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (unreadOnly) params.set("unread_only", "true");
      const data = await api.get(`/api/v1/notifications?${params}`);
      setThreads(data);
    } catch (err) {
      toast.error("Failed to load notifications");
    } finally {
      setLoading(false);
    }
  };

  const selectThread = async (thread) => {
    setSelectedThread(thread);
    try {
      const data = await api.get(`/api/v1/notifications/${thread.thread_id}`);
      setMessages(data);
      // Mark as read
      if (thread.unread_count > 0) {
        await api.post(`/api/v1/notifications/${thread.thread_id}/read`);
        fetchThreads(); // Refresh unread counts
      }
    } catch (err) {
      toast.error("Failed to load thread");
    }
  };

  const openCompose = async () => {
    setShowCompose(true);
    if (customers.length === 0) {
      try {
        const data = await api.get("/api/v1/admin/customers?limit=200");
        const list = Array.isArray(data) ? data : data.items || data.customers || [];
        setCustomers(list);
      } catch {
        // Fallback: admin can type email manually
      }
    }
  };

  const handleCompose = async () => {
    if (!composeRecipient || !composeSubject.trim() || !composeBody.trim()) return;
    setComposeSending(true);
    try {
      await api.post("/api/v1/pro/portal/admin/messages/new", {
        recipient_email: composeRecipient,
        subject: composeSubject,
        body: composeBody,
      });
      toast.success("Message sent");
      setShowCompose(false);
      setComposeRecipient("");
      setComposeSubject("");
      setComposeBody("");
      setCustomerSearch("");
      fetchThreads();
    } catch (err) {
      toast.error(err?.message || "Failed to send message");
    } finally {
      setComposeSending(false);
    }
  };

  const filteredCustomers = customers.filter(c => {
    const q = customerSearch.toLowerCase();
    if (!q) return true;
    return (
      (c.email || "").toLowerCase().includes(q) ||
      (c.company_name || "").toLowerCase().includes(q) ||
      (c.first_name || "").toLowerCase().includes(q) ||
      (c.last_name || "").toLowerCase().includes(q)
    );
  }).slice(0, 20);

  const handleReply = async () => {
    if (!replyText.trim() || !selectedThread) return;
    setSending(true);
    try {
      await api.post(`/api/v1/notifications/${selectedThread.thread_id}/reply`, {
        body: replyText,
      });
      setReplyText("");
      // Refresh thread messages
      const data = await api.get(`/api/v1/notifications/${selectedThread.thread_id}`);
      setMessages(data);
      toast.success("Reply sent");
    } catch (err) {
      toast.error("Failed to send reply");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-white">Messages</h1>
        <div className="flex items-center gap-4">
          {isPro && (
            <button
              type="button"
              onClick={openCompose}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
            >
              + New Message
            </button>
          )}
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              className="rounded bg-gray-800 border-gray-600 text-blue-500 focus:ring-blue-500"
            />
            Unread only
          </label>
        </div>
      </div>

      {/* Compose Overlay */}
      {showCompose && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setShowCompose(false)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">New Message to Customer</h2>
              <button type="button" onClick={() => setShowCompose(false)} className="text-gray-400 hover:text-white">✕</button>
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-1 block">To (customer)</label>
              <input
                type="text"
                value={customerSearch}
                onChange={(e) => { setCustomerSearch(e.target.value); setComposeRecipient(""); }}
                placeholder="Search by name, email, or company..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-2 text-white text-sm placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
              {customerSearch && !composeRecipient && filteredCustomers.length > 0 && (
                <div className="mt-1 max-h-40 overflow-y-auto bg-gray-800 border border-gray-700 rounded-lg">
                  {filteredCustomers.map((c) => (
                    <button
                      type="button"
                      key={c.id || c.email}
                      onClick={() => { setComposeRecipient(c.email); setCustomerSearch(c.company_name ? `${c.company_name} (${c.email})` : c.email); }}
                      className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 transition-colors"
                    >
                      <span className="font-medium">{c.company_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || c.email}</span>
                      {c.company_name && <span className="text-gray-500 ml-2">{c.email}</span>}
                    </button>
                  ))}
                </div>
              )}
              {composeRecipient && (
                <p className="text-xs text-green-400 mt-1">✓ {composeRecipient}</p>
              )}
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-1 block">Subject</label>
              <input
                type="text"
                value={composeSubject}
                onChange={(e) => setComposeSubject(e.target.value)}
                placeholder="Quote follow-up, order update, etc."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-2 text-white text-sm placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-1 block">Message</label>
              <textarea
                value={composeBody}
                onChange={(e) => setComposeBody(e.target.value)}
                placeholder="Type your message..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-2 text-white text-sm placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
                rows={4}
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowCompose(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCompose}
                disabled={!composeRecipient || !composeSubject.trim() || !composeBody.trim() || composeSending}
                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {composeSending ? "Sending..." : "Send"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-4 h-[calc(100%-3rem)]">
        {/* Thread List */}
        <div className="w-1/3 bg-gray-900 border border-gray-800 rounded-xl overflow-y-auto">
          {loading ? (
            <div className="p-4 text-gray-400">Loading...</div>
          ) : threads.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
              No messages yet
            </div>
          ) : (
            threads.map((thread) => (
              <div
                key={thread.thread_id}
                role="button"
                tabIndex={0}
                onClick={() => selectThread(thread)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") selectThread(thread); }}
                className={`w-full text-left p-4 border-b border-gray-800 hover:bg-gray-800/50 transition-colors cursor-pointer ${
                  selectedThread?.thread_id === thread.thread_id ? "bg-gray-800" : ""
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {thread.unread_count > 0 && (
                        <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" />
                      )}
                      <span className={`text-sm font-medium truncate ${thread.unread_count > 0 ? "text-white" : "text-gray-300"}`}>
                        {thread.thread_subject || "No Subject"}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1 truncate">
                      {thread.last_message_preview}
                    </p>
                  </div>
                  <div className="flex flex-col items-end ml-2 flex-shrink-0">
                    <span className="text-xs text-gray-500">
                      {formatTimeAgo(thread.last_message_at)}
                    </span>
                    {thread.sales_order_id && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/admin/orders/${thread.sales_order_id}`);
                        }}
                        className="text-[10px] text-blue-400 hover:text-blue-300 mt-1"
                      >
                        View Order
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Message Detail */}
        <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl flex flex-col">
          {!selectedThread ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              Select a thread to view messages
            </div>
          ) : (
            <>
              {/* Thread Header */}
              <div className="p-4 border-b border-gray-800">
                <h2 className="font-semibold text-white">
                  {selectedThread.thread_subject || "No Subject"}
                </h2>
                <p className="text-xs text-gray-500">
                  {selectedThread.message_count} message{selectedThread.message_count !== 1 ? "s" : ""}
                </p>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`p-3 rounded-lg ${
                      msg.sender_type === "admin"
                        ? "bg-blue-900/30 border border-blue-500/20 ml-8"
                        : "bg-gray-800 border border-gray-700 mr-8"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-gray-400">
                        {msg.sender_name || msg.sender_type}
                      </span>
                      <span className="text-xs text-gray-500">
                        {formatTimeAgo(msg.created_at)}
                      </span>
                    </div>
                    <p className="text-sm text-white whitespace-pre-wrap">{msg.body}</p>
                  </div>
                ))}
              </div>

              {/* Reply Box */}
              <div className="p-4 border-t border-gray-800">
                <div className="flex gap-2">
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder="Type a reply..."
                    className="flex-1 bg-gray-800 border border-gray-700 rounded-lg p-3 text-white text-sm placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
                    rows={2}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleReply();
                      }
                    }}
                  />
                  <button
                    onClick={handleReply}
                    disabled={!replyText.trim() || sending}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed self-end"
                  >
                    {sending ? "..." : "Send"}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
