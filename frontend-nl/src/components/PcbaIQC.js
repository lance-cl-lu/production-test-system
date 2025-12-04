import React, { useMemo, useRef, useState, useCallback, useEffect } from 'react';
import { Card, Form, Input, Button, Space, Table, Tag, Typography, message } from 'antd';
import { translations } from '../i18n/locales';
import { useWebSocket } from '../services/websocket';
import axios from 'axios';

const { Title } = Typography;
const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

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
  const [searchingUid, setSearchingUid] = useState(false);
  const [running, setRunning] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const [testResults, setTestResults] = useState({});
  const timersRef = useRef([]);
  const serialRef = useRef('');
  const lastUidRef = useRef('');

  const [items, setItems] = useState({
    wifi: 'pending',
    firmware: 'pending',
    touch: 'pending',
    bluetooth: 'pending',
    speaker: 'pending',
  });

  // 更新 serialRef 當 serial 改變
  useEffect(() => {
    serialRef.current = serial;
  }, [serial]);

  const normalize = (s) => (s || '').trim();
  const onWsMessage = useCallback((msg) => {
    // Handle UID search events
    if (msg?.type === 'uid_search') {
      const receivedUid = msg.data?.uid;
      if (receivedUid && receivedUid !== lastUidRef.current) {
        lastUidRef.current = receivedUid;
        setSerial(receivedUid);
        setSearchingUid(false);
        message.success(`${pcbaT.uidReceived}: ${receivedUid}`);
      }
      return;
    }
    
    if (msg?.type !== 'pcba_event') return;
    const ev = msg.data;
    setLastEvent(ev);
    if (!ev || !ev.serial) {
      // eslint-disable-next-line no-console
      console.warn('[PCBA] ignore event: missing serial', ev);
      return;
    }
    const incomingSerial = normalize(ev.serial);
    const currentSerial = normalize(serialRef.current);
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
    
    // 儲存測試結果詳細資訊
    if (status === 'pass' || status === 'fail') {
      setTestResults((prev) => ({
        ...prev,
        [key]: {
          status,
          detail: ev.detail,
          timestamp: ev.timestamp || new Date().toISOString(),
        },
      }));
    }
  }, [pcbaT]);

  const { isConnected } = useWebSocket(onWsMessage);

  // 監聽所有測項完成，自動寫入 test_records
  useEffect(() => {
    const allStages = ['wifi', 'firmware', 'touch', 'bluetooth', 'speaker'];
    const allCompleted = allStages.every((s) => items[s] === 'pass' || items[s] === 'fail');
    
    if (allCompleted && running && serial) {
      // 計算整體結果
      const hasFail = allStages.some((s) => items[s] === 'fail');
      const overallResult = hasFail ? 'FAIL' : 'PASS';
      
      // 彙整詳細資料
      const details = {};
      allStages.forEach((stage) => {
        if (testResults[stage]) {
          details[stage] = testResults[stage];
        }
      });

      // 寫入後端
      const saveTestRecord = async () => {
        try {
          const payload = {
            device_id: serial,
            product_name: 'NL_PCBA',
            serial_number: serial,
            test_station: 'PCBA_IQC',
            test_result: overallResult,
            test_time: new Date().toISOString(),
            temperature: 25.0,
            test_data: JSON.stringify(details),
          };
          
          await axios.post(`${API_BASE}/api/test-records/`, payload);
          message.success(`測試完成！結果：${overallResult}，已自動儲存。`);
          console.log('[PCBA] Test record saved:', payload);
        } catch (error) {
          console.error('[PCBA] Failed to save test record:', error);
          message.error('測試結果儲存失敗，請手動記錄。');
        } finally {
          setRunning(false);
        }
      };

      saveTestRecord();
    }
  }, [items, running, serial, testResults]);

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
    setTestResults({});
    setItems({ wifi: 'pending', firmware: 'pending', touch: 'pending', bluetooth: 'pending', speaker: 'pending' });
    lastUidRef.current = ''; // 重置已接收的 UID
  };

  const handleSearch = async () => {
    setSearchingUid(true);
    message.info(pcbaT.searchingUid || 'Searching for UID...');
    
    try {
      // 呼叫後端 uid-search 端點
      await axios.post(`${API_BASE}/api/pcba/uid-search`, {});
      // UID 將透過 WebSocket 接收並自動填入
    } catch (error) {
      console.error('[PCBA] Failed to trigger UID search:', error);
      message.error('搜尋失敗，請檢查連線');
      setSearchingUid(false);
    }
    
    // 設定逾時保護
    setTimeout(() => {
      if (searchingUid) {
        setSearchingUid(false);
        message.warning(pcbaT.searchTimeout || 'UID search timeout');
      }
    }, 30000);
  };

  const runSequential = async () => {
    if (!serial) return message.warning('請先輸入序號');
    
    // 重置狀態
    reset();
    setRunning(true);
    
    if (demoMode) {
      // demo 模式：本地模擬
      const runOne = (key) => new Promise((resolve) => {
        setItems((prev) => ({ ...prev, [key]: 'testing' }));
        const id = setTimeout(() => {
          const ok = Math.random() < 0.8;
          setItems((prev) => ({ ...prev, [key]: ok ? 'pass' : 'fail' }));
          setTestResults((prev) => ({
            ...prev,
            [key]: {
              status: ok ? 'pass' : 'fail',
              detail: { demo: true },
              timestamp: new Date().toISOString(),
            },
          }));
          resolve();
        }, 900);
        timersRef.current.push(id);
      });
      for (const key of ['wifi', 'firmware', 'touch', 'bluetooth', 'speaker']) {
        // eslint-disable-next-line no-await-in-loop
        await runOne(key);
      }
    } else {
      // 正式模式：呼叫後端 start-test API
      try {
        message.info('正在啟動測試，請稍候...');
        await axios.post(`${API_BASE}/api/pcba/start-test`, { serial });
        // 測試結果會透過 WebSocket 逐步更新，完成後自動儲存
      } catch (error) {
        console.error('[PCBA] Failed to start test:', error);
        message.error('啟動測試失敗，請檢查連線或稍後再試。');
        setRunning(false);
      }
    }
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
                <Button 
                  type="default" 
                  onClick={handleSearch} 
                  loading={searchingUid}
                  disabled={running}
                >
                  {pcbaT.search || 'Search'}
                </Button>
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
