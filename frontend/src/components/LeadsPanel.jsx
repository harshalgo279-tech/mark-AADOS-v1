// frontend/src/components/LeadsPanel.jsx
import { useState } from 'react';
import { Phone, FileText, Mail, Linkedin } from 'lucide-react';

const LeadsPanel = ({ leads, onCallLead, onViewDataPacket }) => {
  const [selectedStatus, setSelectedStatus] = useState('all');
  
  const filteredLeads = selectedStatus === 'all' 
    ? leads 
    : leads.filter(l => l.status === selectedStatus);
  
  const getStatusColor = (status) => {
    const colors = {
      'new': '#A2A7AF',
      'data_packet_created': '#2B8AFF',
      'calling': '#9E5AFF',
      'call_completed': '#41FFFF',
      'email_sent': '#41FFFF',
      'demo_booked': '#00FF88'
    };
    return colors[status] || '#A2A7AF';
  };
  
  return (
    <div style={{
      background: 'rgba(10, 13, 16, 0.6)',
      border: '1px solid rgba(65, 255, 255, 0.2)',
      borderRadius: '8px',
      padding: '32px',
      backdropFilter: 'blur(10px)'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px'
      }}>
        <h2 style={{
          fontSize: '18px',
          fontWeight: '700',
          letterSpacing: '2px',
          color: '#F0F3F8',
          textTransform: 'uppercase'
        }}>
          Leads Pipeline ({filteredLeads.length})
        </h2>
        
        <select
          value={selectedStatus}
          onChange={(e) => setSelectedStatus(e.target.value)}
          style={{
            padding: '8px 16px',
            background: 'rgba(14, 17, 22, 0.6)',
            border: '1px solid rgba(65, 255, 255, 0.3)',
            borderRadius: '6px',
            color: '#F0F3F8',
            fontSize: '12px',
            cursor: 'pointer',
            fontFamily: "var(--font-primary)"
          }}
        >
          <option value="all">All Status</option>
          <option value="new">New</option>
          <option value="data_packet_created">Data Packet Created</option>
          <option value="call_completed">Call Completed</option>
          <option value="email_sent">Email Sent</option>
          <option value="demo_booked">Demo Booked</option>
        </select>
      </div>
      
      <div style={{ overflowY: 'auto', maxHeight: '600px' }}>
        {filteredLeads.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '60px 20px',
            color: '#A2A7AF'
          }}>
            {selectedStatus === 'all' 
              ? 'No leads yet. Click "Fetch Leads" to start.'
              : `No leads with status: ${selectedStatus}`
            }
          </div>
        ) : (
          filteredLeads.map((lead) => (
            <div key={lead.id} style={{
              background: 'rgba(14, 17, 22, 0.4)',
              border: '1px solid rgba(65, 255, 255, 0.1)',
              borderRadius: '8px',
              padding: '20px',
              marginBottom: '12px',
              transition: 'all 0.2s ease',
              cursor: 'pointer'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(65, 255, 255, 0.05)';
              e.currentTarget.style.borderColor = 'rgba(65, 255, 255, 0.3)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(14, 17, 22, 0.4)';
              e.currentTarget.style.borderColor = 'rgba(65, 255, 255, 0.1)';
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: '12px'
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{
                    fontSize: '16px',
                    color: '#F0F3F8',
                    fontWeight: '600',
                    marginBottom: '4px'
                  }}>
                    {lead.name}
                  </div>
                  <div style={{
                    fontSize: '13px',
                    color: '#A2A7AF',
                    marginBottom: '8px'
                  }}>
                    {lead.title} at {lead.company}
                  </div>
                  <div style={{
                    display: 'flex',
                    gap: '16px',
                    fontSize: '12px',
                    color: '#5A5F66'
                  }}>
                    <span>{lead.email}</span>
                    {lead.phone && <span>{lead.phone}</span>}
                  </div>
                </div>
                
                <span style={{
                  padding: '6px 14px',
                  borderRadius: '4px',
                  fontSize: '10px',
                  textTransform: 'uppercase',
                  fontWeight: '600',
                  background: `${getStatusColor(lead.status)}20`,
                  color: getStatusColor(lead.status),
                  border: `1px solid ${getStatusColor(lead.status)}40`,
                  letterSpacing: '1px',
                  whiteSpace: 'nowrap'
                }}>
                  {lead.status.replace(/_/g, ' ')}
                </span>
              </div>
              
              <div style={{
                display: 'flex',
                gap: '8px',
                paddingTop: '12px',
                borderTop: '1px solid rgba(65, 255, 255, 0.1)'
              }}>
                {lead.status === 'data_packet_created' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onCallLead(lead.id);
                    }}
                    style={{
                      padding: '8px 16px',
                      border: '1px solid rgba(65, 255, 255, 0.3)',
                      background: 'rgba(65, 255, 255, 0.1)',
                      color: '#41FFFF',
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      letterSpacing: '1px',
                      cursor: 'pointer',
                      borderRadius: '4px',
                      fontFamily: "var(--font-primary)",
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      transition: 'all 0.2s ease'
                    }}
                    onMouseEnter={(e) => {
                      e.target.style.background = 'rgba(65, 255, 255, 0.2)';
                    }}
                    onMouseLeave={(e) => {
                      e.target.style.background = 'rgba(65, 255, 255, 0.1)';
                    }}
                  >
                    <Phone size={12} />
                    Call Now
                  </button>
                )}
                
                {lead.status !== 'new' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewDataPacket(lead.id);
                    }}
                    style={{
                      padding: '8px 16px',
                      border: '1px solid rgba(255, 255, 255, 0.2)',
                      background: 'transparent',
                      color: '#F0F3F8',
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      letterSpacing: '1px',
                      cursor: 'pointer',
                      borderRadius: '4px',
                      fontFamily: "var(--font-primary)",
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
                  >
                    <FileText size={12} />
                    View Packet
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LeadsPanel;