import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import RelativeDate from "./RelativeDate";

/**
 * ShippingTimeline - Displays shipping/tracking event history
 *
 * Shows package journey: label created, picked up, in transit, delivered, etc.
 */

// Event type icons and colors
const eventConfig = {
  label_purchased: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
      </svg>
    ),
    color: "text-blue-400",
    bgColor: "bg-blue-500/20",
  },
  package_created: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
    color: "text-purple-400",
    bgColor: "bg-purple-500/20",
  },
  picked_up: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
      </svg>
    ),
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/20",
  },
  in_transit: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
      </svg>
    ),
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/20",
  },
  out_for_delivery: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    color: "text-orange-400",
    bgColor: "bg-orange-500/20",
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
  delivery_attempted: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: "text-yellow-400",
    bgColor: "bg-yellow-500/20",
  },
  returned: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
      </svg>
    ),
    color: "text-red-400",
    bgColor: "bg-red-500/20",
  },
  exception: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    color: "text-red-400",
    bgColor: "bg-red-500/20",
  },
  address_corrected: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
    color: "text-gray-400",
    bgColor: "bg-gray-500/20",
  },
  customs_cleared: {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2zm9-13.5V9" />
      </svg>
    ),
    color: "text-indigo-400",
    bgColor: "bg-indigo-500/20",
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

// Format location from city, state, zip
function formatLocation(event) {
  const parts = [];
  if (event.location_city) parts.push(event.location_city);
  if (event.location_state) parts.push(event.location_state);
  if (event.location_zip) parts.push(event.location_zip);
  return parts.length > 0 ? parts.join(", ") : null;
}

export default function ShippingTimeline({ orderId, className = "" }) {
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
          `${API_URL}/api/v1/sales-orders/${orderId}/shipping-events`,
          {
            credentials: "include",
          }
        );

        if (!res.ok) {
          throw new Error("Failed to fetch shipping events");
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
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`text-red-400 text-sm py-4 ${className}`}>
        Failed to load shipping events: {error}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className={`text-gray-500 text-sm py-6 text-center ${className}`}>
        No shipping events recorded yet
      </div>
    );
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {events.map((event, index) => {
        const config = eventConfig[event.event_type] || defaultConfig;
        const isLast = index === events.length - 1;
        const location = formatLocation(event);

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
                  {location && (
                    <p className="text-gray-500 text-xs mt-1 flex items-center gap-1">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                      </svg>
                      {location}
                    </p>
                  )}
                  {event.tracking_number && (
                    <p className="text-gray-500 text-xs mt-1">
                      <span className="text-gray-600">Tracking:</span> {event.tracking_number}
                    </p>
                  )}
                </div>
                <div className="text-right flex-shrink-0 ml-4">
                  <RelativeDate
                    date={event.event_timestamp || event.created_at}
                    className="text-gray-500 text-xs"
                  />
                  {event.carrier && (
                    <p className="text-gray-600 text-xs mt-0.5">
                      {event.carrier}
                    </p>
                  )}
                  {event.source && event.source !== "manual" && (
                    <span className="inline-block mt-1 px-1.5 py-0.5 text-[10px] bg-gray-700 text-gray-400 rounded">
                      {event.source === "carrier_api" ? "Carrier API" : event.source}
                    </span>
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
