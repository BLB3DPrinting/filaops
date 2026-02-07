import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import RelativeDate from "./RelativeDate";

/**
 * POActivityTimeline - Displays purchase order activity history
 *
 * Shows a chronological list of events: status changes, receipts, notes, etc.
 */

// Event type icons and colors
const eventConfig = {
  created: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
      </svg>
    ),
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/20",
  },
  status_change: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
      </svg>
    ),
    color: "text-blue-400",
    bgColor: "bg-blue-500/20",
  },
  receipt: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  partial_receipt: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
    ),
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/20",
  },
  note_added: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
    color: "text-gray-400",
    bgColor: "bg-gray-500/20",
  },
  document_attached: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
      </svg>
    ),
    color: "text-purple-400",
    bgColor: "bg-purple-500/20",
  },
  tracking_updated: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/20",
  },
  cancelled: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
    color: "text-red-400",
    bgColor: "bg-red-500/20",
  },
  vendor_contacted: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
    color: "text-indigo-400",
    bgColor: "bg-indigo-500/20",
  },
  price_updated: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-orange-400",
    bgColor: "bg-orange-500/20",
  },
  line_added: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  line_removed: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-red-400",
    bgColor: "bg-red-500/20",
  },
  expected_date_changed: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/20",
  },
};

const defaultConfig = {
  icon: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  color: "text-gray-400",
  bgColor: "bg-gray-500/20",
};

export default function POActivityTimeline({ poId, className = "" }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!poId) return;

    const fetchEvents = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch(
          `${API_URL}/api/v1/purchase-orders/${poId}/events`,
          {
            credentials: "include",
          }
        );

        if (!res.ok) {
          throw new Error("Failed to fetch events");
        }

        const data = await res.json();
        setEvents(data.items || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, [poId]);

  if (loading) {
    return (
      <div className={`flex items-center justify-center py-8 ${className}`}>
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`text-red-400 text-sm py-4 ${className}`}>
        Failed to load activity: {error}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className={`text-gray-500 text-sm py-6 text-center ${className}`}>
        No activity recorded yet
      </div>
    );
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {events.map((event, index) => {
        const config = eventConfig[event.event_type] || defaultConfig;
        const isLast = index === events.length - 1;

        return (
          <div key={event.id} className="flex gap-3">
            {/* Timeline connector */}
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center ${config.bgColor}`}
              >
                <span className={config.color}>{config.icon}</span>
              </div>
              {!isLast && (
                <div className="w-0.5 flex-1 bg-gray-700 mt-2"></div>
              )}
            </div>

            {/* Event content */}
            <div className="flex-1 pb-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-white font-medium text-sm">{event.title}</p>
                  {event.description && (
                    <p className="text-gray-400 text-sm mt-1">
                      {event.description}
                    </p>
                  )}
                  {event.old_value && event.new_value && (
                    <p className="text-gray-500 text-xs mt-1">
                      <span className="text-gray-600">{event.old_value}</span>
                      <span className="mx-2">→</span>
                      <span className={config.color}>{event.new_value}</span>
                    </p>
                  )}
                  {event.metadata_key && event.metadata_value && (
                    <p className="text-gray-500 text-xs mt-1">
                      {event.metadata_key}: {event.metadata_value}
                    </p>
                  )}
                </div>
                <div className="text-right flex-shrink-0 ml-4">
                  <RelativeDate
                    date={event.created_at}
                    className="text-gray-500 text-xs"
                  />
                  {event.user_name && (
                    <p className="text-gray-600 text-xs mt-0.5">
                      by {event.user_name}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
