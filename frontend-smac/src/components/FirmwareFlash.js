import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Col, Input, Row, Space, Typography, message } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import { translations } from '../i18n/locales';
import { testRecordsAPI } from '../services/api';

const { Title, Text } = Typography;

function FirmwareFlash({ language = 'zh-TW', mode = 'hvf' }) {
  const t = translations[language];
  const copy = mode === 'diagnostics' ? t.diagnosticsFlash : t.firmwareFlash;
  const secondaryMcu = mode === 'diagnostics' ? 'WL' : 'WLE';
  const requiresSerialNumber = mode === 'diagnostics';
  const [wbaId, setWbaId] = useState('');
  const [secondaryId, setSecondaryId] = useState('');
  const [serialNumber, setSerialNumber] = useState('');
  const [flashing, setFlashing] = useState(false);
  const [result, setResult] = useState(null);
  const [logs, setLogs] = useState([]);
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: 'end' });
  }, [logs]);

  const handleStart = async () => {
    if (requiresSerialNumber && !/^\d{8}$/.test(serialNumber)) return;

    setWbaId('');
    setSecondaryId('');
    setLogs([]);
    setResult(null);
    setFlashing(true);

    try {
      const firmwareType = mode === 'diagnostics' ? 'diagnostics' : 'test';
      if (requiresSerialNumber) {
        let flashCounts;
        try {
          ({ data: flashCounts } = await testRecordsAPI.getFirmwareFlashCounts(serialNumber));
        } catch {
          throw new Error(copy.historyCheckFailed);
        }

        const previousCount = flashCounts[`${firmwareType}_firmware_count`];
        if (previousCount > 0 && !window.confirm(copy.alreadyFlashed.replace('{count}', String(previousCount)))) {
          return;
        }
      }

      const response = await testRecordsAPI.flashFirmware(mode);
      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(errorBody || `Request failed (${response.status})`);
      }
      if (!response.body) throw new Error(copy.streamUnavailable);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let exitCode = null;
      let detectedWbaId = '';
      let detectedSecondaryId = '';
      const appendLine = (rawLine) => {
        const line = rawLine.replace(/\r$/, '').replace(/\x1B\[[0-9;]*[A-Za-z]/g, '');
        if (!line) return;
        if (line.startsWith('WBA_ID=')) {
          detectedWbaId = line.slice('WBA_ID='.length).trim();
          setWbaId(detectedWbaId);
        }
        const secondaryIdPrefix = `${secondaryMcu}_ID=`;
        if (line.startsWith(secondaryIdPrefix)) {
          detectedSecondaryId = line.slice(secondaryIdPrefix.length).trim();
          setSecondaryId(detectedSecondaryId);
        }
        if (line.startsWith('FLASH_EXIT_CODE=')) {
          exitCode = Number(line.slice('FLASH_EXIT_CODE='.length));
          return;
        }
        setLogs((current) => [...current, line]);
      };

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(appendLine);
        if (done) break;
      }
      if (buffer) appendLine(buffer);
      if (exitCode !== 0) throw new Error(copy.failed);
      if (!detectedWbaId && !detectedSecondaryId) {
        throw new Error(copy.serialsUnavailable);
      }

      try {
        await testRecordsAPI.recordFirmwareFlashSuccess({
          serial_wle: detectedSecondaryId || undefined,
          serial_wba: detectedWbaId || undefined,
          firmware_type: firmwareType,
          diagnostics_number: requiresSerialNumber ? serialNumber : null,
        });
      } catch {
        setResult('error');
        setLogs((current) => [...current, copy.recordFailed]);
        message.error(copy.recordFailed);
        return;
      }

      setResult('success');
      message.success(copy.success);
    } catch (error) {
      const errorMessage = error instanceof TypeError
        ? copy.agentUnavailable
        : error.message;
      setResult('error');
      setLogs((current) => [...current, `${copy.failed}: ${errorMessage}`]);
      message.error(copy.failed);
    } finally {
      setFlashing(false);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ display: 'flex' }}>
      <div>
        <Title level={2} style={{ marginBottom: 4 }}>{copy.title}</Title>
        <Text type="secondary">{copy.description}</Text>
      </div>

      <Card>
        <Row gutter={[12, 12]} align="middle">
          {requiresSerialNumber && (
            <Col xs={24} md={6}>
              <Input
                addonBefore={copy.serialNumberLabel}
                value={serialNumber}
                placeholder={copy.serialNumberPlaceholder}
                inputMode="numeric"
                maxLength={8}
                onChange={(event) => setSerialNumber(event.target.value.replace(/\D/g, '').slice(0, 8))}
              />
            </Col>
          )}
          <Col xs={24} md={requiresSerialNumber ? 6 : 8}>
            <Input addonBefore="WBA" value={wbaId} placeholder={copy.idPlaceholder} readOnly />
          </Col>
          <Col xs={24} md={requiresSerialNumber ? 6 : 8}>
            <Input addonBefore={secondaryMcu} value={secondaryId} placeholder={copy.idPlaceholder} readOnly />
          </Col>
          <Col xs={24} md={requiresSerialNumber ? 6 : 8} style={{ textAlign: 'right' }}>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={flashing}
              disabled={flashing || (requiresSerialNumber && !/^\d{8}$/.test(serialNumber))}
              onClick={handleStart}
              block
            >
              {flashing ? copy.running : copy.start}
            </Button>
          </Col>
        </Row>
      </Card>

      {result === 'success' && <Alert type="success" showIcon message={copy.success} />}
      {result === 'error' && <Alert type="error" showIcon message={copy.failed} />}

      <Card title={copy.logTitle}>
        <div
          role="log"
          aria-live="polite"
          style={{
            height: 280,
            overflowY: 'auto',
            padding: 12,
            background: '#101418',
            color: '#d7e0e8',
            borderRadius: 4,
            fontFamily: 'monospace',
            fontSize: 12,
            whiteSpace: 'pre-wrap',
            overflowWrap: 'anywhere',
          }}
        >
          {logs.length ? logs.map((line, index) => <div key={`${index}-${line}`}>{line}</div>) : copy.logEmpty}
          <div ref={logEndRef} />
        </div>
      </Card>
    </Space>
  );
}

export default FirmwareFlash;
