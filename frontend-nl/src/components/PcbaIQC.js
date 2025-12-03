import React, { useMemo, useRef, useState, useCallback } from 'react';
import { Card, Form, Input, Button, Space, Table, Tag, Typography, message } from 'antd';
import { translations } from '../i18n/locales';
import { useWebSocket } from '../services/websocket';

const { Title } = Typography;

const statusColor = {
  pending: 'default',
  testing: 'processing',
  pass: 'green',
  fail: 'red',
};

const PcbaIQC = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  const pcbaT = t.pcbaIQC;

  const [serial, setSerial] = useState('');
  const [running, setRunning] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const timersRef = useRef([]);

  const [items, setItems] = useState({
    wifi: 'pending',
    firmware: 'pending',
    touch: 'pending',
    bluetooth: 'pending',
    speaker: 'pending',
  });

  const normalize = (s) => (s || '').trim();
  const onWsMessage = useCallback((msg) => {
    if (msg?.type !== 'pcba_event') return;
    const ev = msg.data;
    setLastEvent(ev);
    if (!ev || !ev.serial) {
      // eslint-disable-next-line no-console
      console.warn('[PCBA] ignore event: missing serial', ev);
      return;
    }
    const incomingSerial = normalize(ev.serial);
    const currentSerial = normalize(serial);
    if (incomingSerial !== currentSerial) {
      // eslint-disable-next-line no-console
      console.log('[PCBA] ignore event: serial mismatch', { incomingSerial, currentSerial });
      return;
    }
    const key = ev.stage;
    if (!['wifi','firmware','touch','bluetooth','speaker'].includes(key)) return;
    const status = ev.status;
    if (!['pending','testing','pass','fail'].includes(status)) return;
    // eslint-disable-next-line no-console
    console.log('[PCBA] apply event', { serial: incomingSerial, stage: key, status });
    setItems((prev) => ({ ...prev, [key]: status }));
  }, [serial]);

  const { isConnected } = useWebSocket(onWsMessage);

  const dataSource = useMemo(() => [
    { key: 'wifi', item: pcbaT.items.wifi, status: items.wifi },
    { key: 'firmware', item: pcbaT.items.firmware, status: items.firmware },
    { key: 'touch', item: pcbaT.items.touch, status: items.touch },
    { key: 'bluetooth', item: pcbaT.items.bluetooth, status: items.bluetooth },
    { key: 'speaker', item: pcbaT.items.speaker, status: items.speaker },
  ], [items, pcbaT.items]);

  const columns = [
    { title: pcbaT?.title || 'PCBA IQC', dataIndex: 'item', key: 'item' },
    { 
      title: pcbaT?.resultSummary,
      dataIndex: 'status',
      key: 'status',
      render: (s) => {
        const text = s === 'pending' ? pcbaT.status.pending
          : s === 'testing' ? pcbaT.status.testing
          : s === 'pass' ? pcbaT.status.pass
          : pcbaT.status.fail;
        return <Tag color={statusColor[s]}>{text}</Tag>;
      }
    },
  ];

  const clearTimers = () => {
    timersRef.current.forEach((id) => clearTimeout(id));
    timersRef.current = [];
  };

  const reset = () => {
    clearTimers();
    setRunning(false);
    setItems({ wifi: 'pending', firmware: 'pending', touch: 'pending', bluetooth: 'pending', speaker: 'pending' });
  };

  const runSequential = async () => {
    if (!serial) return message.warning('請先輸入序號');
    if (!demoMode) {
      // 非 demo 模式：僅發送起始請求（未實作觸發端點時僅提示）
      message.info('已準備接收事件。請從 C 程式送 pcba_event。');
      return;
    }
    // demo 模式：本地模擬
    setRunning(true);
    const runOne = (key) => new Promise((resolve) => {
      setItems((prev) => ({ ...prev, [key]: 'testing' }));
      const id = setTimeout(() => {
        const ok = Math.random() < 0.8;
        setItems((prev) => ({ ...prev, [key]: ok ? 'pass' : 'fail' }));
        resolve();
      }, 900);
      timersRef.current.push(id);
    });
    for (const key of ['wifi', 'firmware', 'touch', 'bluetooth', 'speaker']) {
      // eslint-disable-next-line no-await-in-loop
      await runOne(key);
    }
    setRunning(false);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>{pcbaT.title}</Title>
          <Form layout="inline" onFinish={runSequential}>
            <Form.Item label={pcbaT.enterSerialNumber}>
              <Input
                placeholder={pcbaT.enterSerialNumber}
                value={serial}
                onChange={(e) => setSerial(e.target.value)}
                style={{ width: 260 }}
                disabled={running}
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" disabled={!serial || running}>{pcbaT.startTest}</Button>
                <Button onClick={reset} disabled={running}>{pcbaT.reset}</Button>
                <Button onClick={() => setDemoMode((v) => !v)} disabled={running}>
                  {demoMode ? '關閉Demo' : '啟用Demo'}
                </Button>
              </Space>
            </Form.Item>
          </Form>
          <div style={{ fontSize: 12, color: isConnected ? '#3f8600' : '#cf1322' }}>
            WS {isConnected ? 'connected' : 'disconnected'}
          </div>
        </Space>
      </Card>

      <Card title={pcbaT.resultSummary}>
        <Table
          rowKey={(r) => r.key}
          columns={columns}
          dataSource={dataSource}
          pagination={false}
        />
      </Card>

      <Card title="Debug: Last Event" size="small">
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
{lastEvent ? JSON.stringify(lastEvent, null, 2) : 'No events yet'}
        </pre>
      </Card>
    </Space>
  );
};

export default PcbaIQC;
