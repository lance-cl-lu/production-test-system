import React, { useMemo, useRef, useState } from 'react';
import { Card, Form, Input, Button, Space, Table, Tag, Typography } from 'antd';
import { translations } from '../i18n/locales';

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
  const timersRef = useRef([]);

  const [items, setItems] = useState({
    wifi: 'pending',
    firmware: 'pending',
    touch: 'pending',
    bluetooth: 'pending',
    speaker: 'pending',
  });

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
    if (!serial) return;
    setRunning(true);

    const runOne = (key) => new Promise((resolve) => {
      setItems((prev) => ({ ...prev, [key]: 'testing' }));
      const id = setTimeout(() => {
        // 模擬結果（80% PASS, 20% FAIL）
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
              </Space>
            </Form.Item>
          </Form>
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
    </Space>
  );
};

export default PcbaIQC;
