class WebSocketManager {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 3000;
  }

  // ✅ compatibility: your App.jsx uses wsManager.on(...)
  on(eventType, callback) {
    this.addListener(eventType, callback);
  }

  // ✅ compatibility: optional if you ever use wsManager.off(...)
  off(eventType, callback) {
    this.removeListener(eventType, callback);
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.notifyListeners("connected", { status: "connected" });
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.notifyListeners(data.type, data);
        } catch (error) {
          console.error("Error parsing WebSocket message:", error);
        }
      };

      this.ws.onclose = () => {
        this.notifyListeners("disconnected", { status: "disconnected" });
        this.handleReconnect();
      };

      this.ws.onerror = (error) => {
        this.notifyListeners("error", { error });
      };
    } catch (error) {
      this.handleReconnect();
    }
  }

  handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), this.reconnectDelay);
    } else {
      this.notifyListeners("reconnect_failed", { status: "failed" });
    }
  }

  addListener(eventType, callback) {
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
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export default WebSocketManager;
