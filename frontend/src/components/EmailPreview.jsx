// frontend/src/components/EmailPreview.jsx
import { Mail, Send, Clock } from 'lucide-react';

const EmailPreview = ({ email, onClose }) => {
  if (!email) return null;
  
  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.85)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(8px)',
      padding: '40px'
    }}>
      <div style={{
        background: '#FFFFFF',
        borderRadius: '12px',
        maxWidth: '700px',
        width: '100%',
        maxHeight: '90vh',
        overflow: 'auto',
        boxShadow: '0 0 60px rgba(0, 0, 0, 0.5)'
      }}>
        {/* Email Header */}
        <div style={{
          background: 'linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)',
          padding: '24px',
          borderTopLeftRadius: '12px',
          borderTopRightRadius: '12px',
          borderBottom: '2px solid #41FFFF'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Mail size={24} style={{ color: '#41FFFF' }} />
              <h3 style={{ fontSize: '20px', color: '#F0F3F8', fontWeight: '600' }}>
                Follow-up Email
              </h3>
            </div>
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                background: 'transparent',
                color: '#F0F3F8',
                cursor: 'pointer',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            >
              Close
            </button>
          </div>
          
          <div style={{
            marginTop: '16px',
            padding: '12px',
            background: 'rgba(65, 255, 255, 0.1)',
            borderRadius: '6px',
            display: 'flex',
            gap: '16px',
            fontSize: '13px',
            color: '#A2A7AF'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Clock size={14} />
              {email.sent_at ? new Date(email.sent_at).toLocaleString() : 'Pending'}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Send size={14} />
              Status: <span style={{ color: email.status === 'sent' ? '#00FF88' : '#FF9500' }}>
                {email.status}
              </span>
            </div>
          </div>
        </div>
        
        {/* Email Content */}
        <div style={{ padding: '32px', color: '#333' }}>
          <div style={{ marginBottom: '24px' }}>
            <div style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>
              <strong>Subject:</strong>
            </div>
            <div style={{ fontSize: '16px', fontWeight: '600', color: '#000' }}>
              {email.subject}
            </div>
          </div>
          
          <div style={{
            borderTop: '1px solid #E0E0E0',
            paddingTop: '24px',
            lineHeight: '1.8',
            fontSize: '14px',
            color: '#333'
          }}
            dangerouslySetInnerHTML={{ __html: email.body_html }}
          />
          
          {email.pdf_attached && (
            <div style={{
              marginTop: '24px',
              padding: '16px',
              background: '#F5F5F5',
              borderRadius: '8px',
              border: '1px solid #E0E0E0'
            }}>
              <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>
                📎 Attachment:
              </div>
              <div style={{ fontSize: '14px', color: '#2B8AFF', fontWeight: '500' }}>
                Call_Report_1Pager.pdf
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EmailPreview;