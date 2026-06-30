import { useState, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

/** Talks to the IntelliAdmit FastAPI /chat endpoint. */
export function useChat(profile, threadId = "web-user") {
  const [messages, setMessages] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const send = useCallback(
    async (query) => {
      setMessages((m) => [...m, { role: "user", content: query }]);
      setLoading(true);
      try {
        const res = await fetch(`${API}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, profile, thread_id: threadId }),
        });
        const data = await res.json();
        setResult(data);
        setMessages((m) => [...m, { role: "assistant", content: data.response }]);
      } catch (e) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: "Error reaching the API. Is uvicorn running?" },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [profile, threadId]
  );

  return { messages, result, loading, send };
}
