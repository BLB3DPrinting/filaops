import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import RelativeDate from "./RelativeDate";

/**
 * ActivityTimeline - Displays order activity history
 *
 * Shows a chronological list of events: status changes, notes,
 * payments, shipping updates, etc.
 */

// Event type icons and colors
const eventConfig = {
  status_change: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
      </svg>
    ),
    color: "text-blue-400",
    bgColor: "bg-blue-500/20",
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
  payment_received: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  payment_refunded: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
      </svg>
    ),
    color: "text-red-400",
    bgColor: "bg-red-500/20",
  },
  production_started: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-purple-400",
    bgColor: "bg-purple-500/20",
  },
  production_completed: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  qc_passed: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  qc_failed: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    color: "text-red-400",
    bgColor: "bg-red-500/20",
  },
  shipped: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
    ),
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/20",
  },
  delivered: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  address_updated: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    color: "text-gray-400",
    bgColor: "bg-gray-500/20",
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
  on_hold: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/20",
  },
  resumed: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-green-400",
    bgColor: "bg-green-500/20",
  },
  created: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
      </svg>
    ),
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/20",
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

export default function ActivityTimeline({ orderId, className = "" }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!orderId) return;

    const fetchEvents = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch(
          `${API_URL}/api/v1/sales-orders/${orderId}/events`,
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
  }, [orderId]);

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
