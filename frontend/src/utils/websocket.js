// frontend/src/utils/websocket.js
class WebSocketManager {
  constructor(url) {
    this.url = url;
    this.ws = null;

    this.listeners = new Map();

    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.baseReconnectDelay = 800; // ms
    this.maxReconnectDelay = 8000; // ms

    this._manualClose = false;
    this._closeOnOpen = false;
    this._reconnectTimer = null;
  }

  on(eventType, callback) {
    this.addListener(eventType, callback);
  }

  off(eventType, callback) {
    this.removeListener(eventType, callback);
  }

  connect() {
    // prevent duplicate connects
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this._manualClose = false;
    this._closeOnOpen = false;

    try {
      const ws = new WebSocket(this.url);
      this.ws = ws;

      ws.onopen = () => {
        // If React strict cleanup tried to close while connecting, close AFTER open
        if (this._closeOnOpen || this._manualClose) {
          try {
            ws.close(1000, "client-close");
          } catch {}
          return;
        }

        this.reconnectAttempts = 0;
        this.notifyListeners("connected", { status: "connected" });
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.notifyListeners(data?.type, data);
        } catch (error) {
          console.error("Error parsing WebSocket message:", error);
        }
      };

      ws.onclose = () => {
        this.notifyListeners("disconnected", { status: "disconnected" });
        if (!this._manualClose) this.handleReconnect();
      };

      ws.onerror = (error) => {
        this.notifyListeners("error", { error });
        // don't force-close here; let onclose handle reconnect if it actually closes
      };
    } catch {
      this.handleReconnect();
    }
  }

  handleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.notifyListeners("reconnect_failed", { status: "failed" });
      return;
    }

    this.reconnectAttempts += 1;

    const backoff = Math.min(
      this.maxReconnectDelay,
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    );

    const delay = Math.floor(backoff * (0.8 + Math.random() * 0.4)); // jitter

    this.notifyListeners("reconnecting", { attempt: this.reconnectAttempts, delay });

    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  addListener(eventType, callback) {
    if (!eventType || typeof callback !== "function") return;
    if (!this.listeners.has(eventType)) this.listeners.set(eventType, []);
    this.listeners.get(eventType).push(callback);
  }

  removeListener(eventType, callback) {
    if (!this.listeners.has(eventType)) return;
    const arr = this.listeners.get(eventType);
    const idx = arr.indexOf(callback);
    if (idx > -1) arr.splice(idx, 1);
  }

  notifyListeners(eventType, data) {
    if (!eventType) return;
    const arr = this.listeners.get(eventType);
    if (!arr) return;
    for (const cb of arr) {
      try {
        cb(data);
      } catch (e) {
        console.error("WebSocket listener error:", e);
      }
    }
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  disconnect() {
    this._manualClose = true;
    clearTimeout(this._reconnectTimer);

    if (!this.ws) return;

    // KEY: don't close while CONNECTING (causes browser warning)
    if (this.ws.readyState === WebSocket.CONNECTING) {
      this._closeOnOpen = true;
      return;
    }

    try {
      this.ws.close(1000, "client-close");
    } catch {}
    this.ws = null;
  }
}

export default WebSocketManager;
