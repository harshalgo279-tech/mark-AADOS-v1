// frontend/src/components/DataPacketViewer.jsx
import { FileText, Target, Lightbulb, TrendingUp } from 'lucide-react';

const DataPacketViewer = ({ dataPacket, onClose }) => {
  if (!dataPacket) return null;
  
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
        background: 'linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)',
        border: '2px solid #2B8AFF',
        borderRadius: '16px',
        padding: '40px',
        maxWidth: '900px',
        width: '100%',
        maxHeight: '90vh',
        overflow: 'auto',
        boxShadow: '0 0 60px rgba(43, 138, 255, 0.3)'
      }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '32px'
        }}>
          <h2 style={{
            fontSize: '24px',
            color: '#F0F3F8',
            fontWeight: '700',
            letterSpacing: '1px'
          }}>
            Data Packet
          </h2>
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
        
        {/* Company Analysis */}
        <div style={{ marginBottom: '32px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '16px'
          }}>
            <FileText size={20} style={{ color: '#2B8AFF' }} />
            <h3 style={{ fontSize: '18px', color: '#2B8AFF', fontWeight: '600' }}>
              Company Analysis
            </h3>
          </div>
          <p style={{
            color: '#A2A7AF',
            lineHeight: '1.8',
            padding: '16px',
            background: 'rgba(43, 138, 255, 0.05)',
            borderRadius: '8px',
            border: '1px solid rgba(43, 138, 255, 0.2)'
          }}>
            {dataPacket.company_analysis}
          </p>
        </div>
        
        {/* Use Cases */}
        <div style={{ marginBottom: '32px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '16px'
          }}>
            <Target size={20} style={{ color: '#41FFFF' }} />
            <h3 style={{ fontSize: '18px', color: '#41FFFF', fontWeight: '600' }}>
              Use Cases
            </h3>
          </div>
          
          {dataPacket.use_cases?.map((useCase, idx) => (
            <div key={idx} style={{
              marginBottom: '20px',
              padding: '20px',
              background: 'rgba(65, 255, 255, 0.05)',
              borderRadius: '8px',
              border: '1px solid rgba(65, 255, 255, 0.2)'
            }}>
              <h4 style={{
                fontSize: '16px',
                color: '#F0F3F8',
                fontWeight: '600',
                marginBottom: '12px'
              }}>
                {idx + 1}. {useCase.title}
              </h4>
              <p style={{
                color: '#A2A7AF',
                fontSize: '14px',
                marginBottom: '12px',
                lineHeight: '1.6'
              }}>
                {useCase.description}
              </p>
              <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                padding: '12px',
                background: 'rgba(65, 255, 255, 0.1)',
                borderRadius: '6px'
              }}>
                <TrendingUp size={16} style={{ color: '#41FFFF', marginTop: '2px' }} />
                <span style={{ color: '#41FFFF', fontSize: '13px', fontStyle: 'italic' }}>
                  {useCase.impact}
                </span>
              </div>
            </div>
          ))}
        </div>
        
        {/* Solutions */}
        <div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '16px'
          }}>
            <Lightbulb size={20} style={{ color: '#9E5AFF' }} />
            <h3 style={{ fontSize: '18px', color: '#9E5AFF', fontWeight: '600' }}>
              Algonox Solutions
            </h3>
          </div>
          
          {dataPacket.solutions?.map((solution, idx) => (
            <div key={idx} style={{
              marginBottom: '20px',
              padding: '20px',
              background: 'rgba(158, 90, 255, 0.05)',
              borderRadius: '8px',
              border: '1px solid rgba(158, 90, 255, 0.2)'
            }}>
              <h4 style={{
                fontSize: '16px',
                color: '#F0F3F8',
                fontWeight: '600',
                marginBottom: '12px'
              }}>
                {solution.title}
              </h4>
              <p style={{
                color: '#A2A7AF',
                fontSize: '14px',
                marginBottom: '12px',
                lineHeight: '1.6'
              }}>
                {solution.description}
              </p>
              <div style={{
                padding: '10px',
                background: 'rgba(158, 90, 255, 0.1)',
                borderRadius: '6px',
                fontSize: '13px',
                color: '#9E5AFF',
                fontWeight: '500'
              }}>
                ROI: {solution.roi}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default DataPacketViewer;