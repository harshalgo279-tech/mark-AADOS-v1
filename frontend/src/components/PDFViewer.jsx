// frontend/src/components/PDFViewer.jsx
import { X, Download } from 'lucide-react';

const PDFViewer = ({ pdfUrl, onClose }) => {
  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.9)',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 1000,
      padding: '20px'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px',
        padding: '0 20px'
      }}>
        <h3 style={{ color: '#F0F3F8', fontSize: '20px' }}>
          1-Pager Report
        </h3>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={() => window.open(pdfUrl, '_blank')}
            style={{
              padding: '10px 20px',
              border: '1px solid #41FFFF',
              background: 'rgba(65, 255, 255, 0.1)',
              color: '#41FFFF',
              cursor: 'pointer',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '12px',
              fontFamily: "var(--font-primary)"
            }}
          >
            <Download size={16} />
            Download
          </button>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              background: 'transparent',
              color: '#F0F3F8',
              cursor: 'pointer',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '12px'
            }}
          >
            <X size={16} />
            Close
          </button>
        </div>
      </div>
      
      <iframe
        src={pdfUrl}
        style={{
          flex: 1,
          border: '2px solid #41FFFF',
          borderRadius: '8px',
          background: '#FFF'
        }}
        title="PDF Viewer"
      />
    </div>
  );
};

export default PDFViewer;