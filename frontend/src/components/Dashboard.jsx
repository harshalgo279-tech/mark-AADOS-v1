import { useState, useEffect } from 'react';
import { Phone, Users, FileText, Mail, Loader, CheckCircle, XCircle, Activity, RefreshCw } from 'lucide-react';
import CallMonitor from './CallMonitor';
import DataPacketViewer from './DataPacketViewer';
import EmailPreview from './EmailPreview';
import LeadsPanel from './LeadsPanel';
import WebSocketManager from '../utils/websocket';
import { leadsAPI, callsAPI, reportsAPI } from '../utils/api';
import '../styles/globals.css';

const Dashboard = () => {
  const [leads, setLeads] = useState([]);
  const [calls, setCalls] = useState([]);
  const [metrics, setMetrics] = useState({
    totalLeads: 0,
    dataPacketsCreated: 0,
    callsMade: 0,
    pdfsGenerated: 0,
    emailsSent: 0
  });
  const [activityLog, setActivityLog] = useState([]);
  const [loading, setLoading] = useState(false);
  
  // Modal states
  const [showCallMonitor, setShowCallMonitor] = useState(false);
  const [currentCall, setCurrentCall] = useState(null);
  const [selectedDataPacket, setSelectedDataPacket] = useState(null);
  const [selectedEmail, setSelectedEmail] = useState(null);
  
  // WebSocket
  const [wsManager] = useState(() => new WebSocketManager('ws://localhost:8000/ws'));
  const [wsConnected, setWsConnected] = useState(false);
  
  useEffect(() => {
    initializeApp();
    
    return () => {
      wsManager.disconnect();
    };
  }, []);
  
  const initializeApp = async () => {
    // Setup WebSocket
    wsManager.on('connected', () => {
      setWsConnected(true);
      addActivity('System connected', 'success');
    });
    
    wsManager.on('disconnected', () => {
      setWsConnected(false);
      addActivity('System disconnected', 'error');
    });
    
    wsManager.on('status', (data) => {
      addActivity(data.message, 'info');
    });
    
    wsManager.on('leads_fetched', (data) => {
      addActivity(`Fetched ${data.count} leads from Apollo`, 'success');
      loadLeads();
    });
    
    wsManager.on('data_packet_creating', (data) => {
      addActivity(`Creating data packet for ${data.company}...`, 'info');
    });
    
    wsManager.on('data_packet_created', (data) => {
      addActivity(`Data packet created for ${data.company}`, 'success');
      loadLeads();
      setMetrics(m => ({ ...m, dataPacketsCreated: m.dataPacketsCreated + 1 }));
    });
    
    wsManager.on('call_initiating', (data) => {
      addActivity(`Initiating call to ${data.lead_name} at ${data.company}...`, 'info');
      setCurrentCall({
        id: null,
        lead_name: data.lead_name,
        company: data.company,
        status: 'initiating'
      });
      setShowCallMonitor(true);
    });
    
    wsManager.on('call_started', (data) => {
      addActivity(`Call started (Call ID: ${data.call_id})`, 'success');
      setCurrentCall(prev => ({
        ...prev,
        id: data.call_id,
        status: 'in-progress'
      }));
      setMetrics(m => ({ ...m, callsMade: m.callsMade + 1 }));
    });
    
    wsManager.on('call_ringing', (data) => {
      addActivity('Call is ringing...', 'info');
      setCurrentCall(prev => ({ ...prev, status: 'ringing' }));
    });
    
    wsManager.on('call_in_progress', (data) => {
      addActivity('Call connected - conversation in progress', 'success');
      setCurrentCall(prev => ({ ...prev, status: 'in-progress' }));
    });
    
    wsManager.on('call_completed', (data) => {
      addActivity(`Call completed (Duration: ${data.duration}s)`, 'success');
      setCurrentCall(prev => ({ ...prev, status: 'completed' }));
    });
    
    wsManager.on('call_analyzed', (data) => {
      addActivity(`Call analyzed - Sentiment: ${data.sentiment}, Interest: ${data.interest_level}`, 'success');
    });
    
    wsManager.on('pdf_generating', () => {
      addActivity('Generating 1-pager PDF...', 'info');
    });
    
    wsManager.on('pdf_generated', () => {
      addActivity('PDF generated successfully', 'success');
      setMetrics(m => ({ ...m, pdfsGenerated: m.pdfsGenerated + 1 }));
    });
    
    wsManager.on('linkedin_generating', () => {
      addActivity('Generating LinkedIn scripts...', 'info');
    });
    
    wsManager.on('linkedin_generated', () => {
      addActivity('LinkedIn scripts ready', 'success');
    });
    
    wsManager.on('email_sending', () => {
      addActivity('Sending follow-up email...', 'info');
    });
    
    wsManager.on('email_sent', () => {
      addActivity('Follow-up email sent', 'success');
      setMetrics(m => ({ ...m, emailsSent: m.emailsSent + 1 }));
    });
    
    wsManager.on('workflow_complete', () => {
      addActivity('Complete workflow finished! 🎉', 'success');
      setShowCallMonitor(false);
      setCurrentCall(null);
      loadDashboardData();
    });
    
    wsManager.connect();
    
    // Load initial data
    await loadDashboardData();
  };
  
  const addActivity = (message, type) => {
    const activity = {
      id: Date.now(),
      message,
      type,
      timestamp: new Date().toLocaleTimeString()
    };
    setActivityLog(prev => [activity, ...prev].slice(0, 100));
  };
  
  const loadDashboardData = async () => {
    try {
      await Promise.all([
        loadLeads(),
        loadCalls(),
        loadMetrics()
      ]);
    } catch (error) {
      console.error('Error loading dashboard:', error);
      addActivity('Error loading dashboard data', 'error');
    }
  };
  
  const loadLeads = async () => {
    try {
      const response = await leadsAPI.getAll();
      setLeads(response.data);
    } catch (error) {
      console.error('Error loading leads:', error);
    }
  };
  
  const loadCalls = async () => {
    try {
      const response = await callsAPI.getAll();
      setCalls(response.data);
    } catch (error) {
      console.error('Error loading calls:', error);
    }
  };
  
  const loadMetrics = async () => {
    try {
      const response = await reportsAPI.getDashboard();
      setMetrics({
        totalLeads: response.data.leads.total,
        dataPacketsCreated: response.data.leads.data_packets_created,
        callsMade: response.data.calls.total,
        pdfsGenerated: response.data.pdfs.generated,
        emailsSent: response.data.emails.sent
      });
    } catch (error) {
      console.error('Error loading metrics:', error);
    }
  };
  
  const handleFetchLeads = async () => {
    try {
      setLoading(true);
      const response = await leadsAPI.fetch({ limit: 20 });
      addActivity(response.data.message, 'success');
    } catch (error) {
      addActivity('Error fetching leads', 'error');
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const handleCallLead = async (leadId) => {
    try {
      const response = await leadsAPI.initiateCall(leadId);
      addActivity(response.data.message, 'success');
    } catch (error) {
      addActivity('Error initiating call', 'error');
      console.error('Error:', error);
    }
  };
  
  const handleViewDataPacket = async (leadId) => {
    try {
      const response = await leadsAPI.getDataPacket(leadId);
      setSelectedDataPacket(response.data);
    } catch (error) {
      addActivity('Error loading data packet', 'error');
      console.error('Error:', error);
    }
  };
  
  const getActivityIcon = (type) => {
    switch (type) {
      case 'success': return <CheckCircle size={16} style={{ color: '#41FFFF' }} />;
      case 'error': return <XCircle size={16} style={{ color: '#FF244E' }} />;
      default: return <Activity size={16} style={{ color: '#2B8AFF' }} />;
    }
  };
  
  return (
    <div style={{
      width: '100vw',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #050507 0%, #0A0D10 50%, #0E1116 100%)',
      position: 'relative',
      padding: '40px',
      fontFamily: "'Orbitron', sans-serif"
    }}>
      {/* Grid Background */}
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        backgroundImage: 'linear-gradient(rgba(65, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(65, 255, 255, 0.03) 1px, transparent 1px)',
        backgroundSize: '50px 50px',
        pointerEvents: 'none',
        zIndex: 0
      }} />
      
      {/* Content */}
      <div style={{ position: 'relative', zIndex: 1, maxWidth: '1800px', margin: '0 auto' }}>
        
        {/* Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '40px'
        }}>
          <div>
            <h1 style={{
              fontSize: '48px',
              fontWeight: '800',
              letterSpacing: '4px',
              background: 'linear-gradient(135deg, #41FFFF 0%, #2B8AFF 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              marginBottom: '8px'
            }}>
              ALGONOX AADOS
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <p style={{
                fontSize: '14px',
                color: '#A2A7AF',
                letterSpacing: '2px'
              }}>
                AI Agents Driven Outbound Sales
              </p>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: wsConnected ? '#00FF88' : '#FF244E',
                boxShadow: `0 0 10px ${wsConnected ? '#00FF88' : '#FF244E'}`
              }} />
              <span style={{ fontSize: '11px', color: wsConnected ? '#00FF88' : '#FF244E' }}>
                {wsConnected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={loadDashboardData}
              style={{
                padding: '14px 20px',
                border: '2px solid rgba(255, 255, 255, 0.2)',
                background: 'transparent',
                color: '#F0F3F8',
                cursor: 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '1px',
                fontSize: '12px',
                fontWeight: '600',
                fontFamily: "'Orbitron', sans-serif",
                transition: 'all 0.3s ease',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <RefreshCw size={16} />
              Refresh
            </button>
            
            <button
              onClick={handleFetchLeads}
              disabled={loading}
              style={{
                padding: '14px 32px',
                border: '2px solid #41FFFF',
                background: loading ? 'rgba(65, 255, 255, 0.1)' : 'transparent',
                color: '#41FFFF',
                cursor: loading ? 'not-allowed' : 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '2px',
                fontSize: '12px',
                fontWeight: '600',
                fontFamily: "'Orbitron', sans-serif",
                transition: 'all 0.3s ease',
                opacity: loading ? 0.5 : 1,
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              {loading ? (
                <>
                  <Loader size={16} style={{ animation: 'spin 1s linear infinite' }} />
                  Processing
                </>
              ) : (
                'Fetch Leads'
              )}
            </button>
          </div>
        </div>
        
        {/* Metrics */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: '20px',
          marginBottom: '40px'
        }}>
          {[
            { icon: Users, label: 'Total Leads', value: metrics.totalLeads, color: '#41FFFF' },
            { icon: FileText, label: 'Data Packets', value: metrics.dataPacketsCreated, color: '#2B8AFF' },
            { icon: Phone, label: 'Calls Made', value: metrics.callsMade, color: '#9E5AFF' },
            { icon: FileText, label: 'PDFs Generated', value: metrics.pdfsGenerated, color: '#FF9500' },
            { icon: Mail, label: 'Emails Sent', value: metrics.emailsSent, color: '#FF244E' }
          ].map((metric, idx) => (
            <div key={idx} style={{
              background: 'rgba(10, 13, 16, 0.6)',
              border: `1px solid ${metric.color}40`,
              borderRadius: '8px',
              padding: '24px',
              backdropFilter: 'blur(10px)',
              transition: 'all 0.3s ease',
              cursor: 'pointer',
              position: 'relative',
              overflow: 'hidden'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-4px)';
              e.currentTarget.style.borderColor = `${metric.color}80`;
              e.currentTarget.style.boxShadow = `0 8px 30px ${metric.color}40`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.borderColor = `${metric.color}40`;
              e.currentTarget.style.boxShadow = 'none';
            }}>
              <div style={{
                position: 'absolute',
                top: '-50%',
                left: '-50%',
                width: '200%',
                height: '200%',
                background: `radial-gradient(circle, ${metric.color}20 0%, transparent 70%)`,
                pointerEvents: 'none'
              }} />
              
              <div style={{ position: 'relative', zIndex: 1 }}>
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '50%',
                  border: `2px solid ${metric.color}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '16px',
                  background: `${metric.color}10`
                }}>
                  <metric.icon size={24} style={{ color: metric.color }} />
                </div>
                
                <div style={{
                  fontSize: '32px',
                  fontWeight: '800',
                  color: '#F0F3F8',
                  marginBottom: '8px'
                }}>
                  {metric.value}
                </div>
                
                <div style={{
                  fontSize: '11px',
                  color: '#A2A7AF',
                  textTransform: 'uppercase',
                  letterSpacing: '2px'
                }}>
                  {metric.label}
                </div>
              </div>
            </div>
          ))}
        </div>
        
        {/* Main Content Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr',
          gap: '24px'
        }}>
          
          {/* Leads Panel */}
          <LeadsPanel 
            leads={leads}
            onCallLead={handleCallLead}
            onViewDataPacket={handleViewDataPacket}
          />
          
          {/* Activity Log */}
          <div style={{
            background: 'rgba(10, 13, 16, 0.6)',
            border: '1px solid rgba(43, 138, 255, 0.2)',
            borderRadius: '8px',
            padding: '32px',
            backdropFilter: 'blur(10px)',
            maxHeight: '700px',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <h2 style={{
              fontSize: '18px',
              fontWeight: '700',
              letterSpacing: '2px',
              color: '#F0F3F8',
              marginBottom: '24px',
              textTransform: 'uppercase'
            }}>
              Live Activity Monitor
            </h2>
            
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {activityLog.map((activity) => (
                <div key={activity.id} style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  marginBottom: '16px',
                  padding: '12px',
                  background: 'rgba(14, 17, 22, 0.3)',
                  borderRadius: '6px',
                  borderLeft: `3px solid ${
                    activity.type === 'success' ? '#41FFFF' : 
                    activity.type === 'error' ? '#FF244E' : '#2B8AFF'
                  }`
                }}>
                  {getActivityIcon(activity.type)}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', color: '#F0F3F8', marginBottom: '4px' }}>
                      {activity.message}
                    </div>
                    <div style={{ fontSize: '10px', color: '#5A5F66' }}>
                      {activity.timestamp}
                    </div>
                  </div>
                </div>
              ))}
              
              {activityLog.length === 0 && (
                <div style={{
                  textAlign: 'center',
                  padding: '60px 20px',
                  color: '#A2A7AF'
                }}>
                  Waiting for activity...
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Modals */}
      {showCallMonitor && currentCall && (
        <CallMonitor 
          call={currentCall}
          onClose={() => setShowCallMonitor(false)}
        />
      )}
      
      {selectedDataPacket && (
        <DataPacketViewer
          dataPacket={selectedDataPacket}
          onClose={() => setSelectedDataPacket(null)}
        />
      )}
      
      {selectedEmail && (
        <EmailPreview
          email={selectedEmail}
          onClose={() => setSelectedEmail(null)}
        />
      )}
      
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default Dashboard;