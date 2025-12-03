import React, { useState } from 'react';
import { Card, Form, Input, Select, DatePicker, Button, Space, Table, Tag } from 'antd';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;
const { Option } = Select;

// 初版：先複製「閘道器進料檢驗」的結構（可再調整差異）
const PcbaIQC = () => {
  const [filters, setFilters] = useState({
    serial_number: '',
    lot_no: '',
    iqc_result: null,
    dateRange: null,
  });
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);

  const columns = [
    { title: '序號', dataIndex: 'serial_number', key: 'serial_number' },
    { title: '批號', dataIndex: 'lot_no', key: 'lot_no' },
    { title: '料號', dataIndex: 'part_no', key: 'part_no' },
    { title: '檢驗結果', dataIndex: 'iqc_result', key: 'iqc_result', render: (v) => <Tag color={v === 'PASS' ? 'green' : 'red'}>{v || '-'}</Tag> },
    { title: '檢驗時間', dataIndex: 'iqc_time', key: 'iqc_time', render: (t) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '-') },
  ];

  const query = async () => {
    setLoading(true);
    // TODO: 呼叫實際 API：/api/pcba-iqc（目前佔位）
    // 先放假資料，之後接上後端路由
    setTimeout(() => {
      setRecords([
        { id: 1, serial_number: 'SN123', lot_no: 'LOT-A1', part_no: 'P-001', iqc_result: 'PASS', iqc_time: new Date().toISOString() },
        { id: 2, serial_number: 'SN124', lot_no: 'LOT-A1', part_no: 'P-002', iqc_result: 'FAIL', iqc_time: new Date().toISOString() },
      ]);
      setLoading(false);
    }, 500);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="PCBA進料檢驗 - 查詢條件">
        <Form layout="inline" onFinish={query}>
          <Form.Item label="序號">
            <Input
              placeholder="序號"
              value={filters.serial_number}
              onChange={(e) => setFilters({ ...filters, serial_number: e.target.value })}
              style={{ width: 200 }}
            />
          </Form.Item>
          <Form.Item label="批號">
            <Input
              placeholder="批號"
              value={filters.lot_no}
              onChange={(e) => setFilters({ ...filters, lot_no: e.target.value })}
              style={{ width: 160 }}
            />
          </Form.Item>
          <Form.Item label="檢驗結果">
            <Select
              placeholder="選擇"
              allowClear
              value={filters.iqc_result}
              onChange={(v) => setFilters({ ...filters, iqc_result: v })}
              style={{ width: 140 }}
            >
              <Option value="PASS">PASS</Option>
              <Option value="FAIL">FAIL</Option>
            </Select>
          </Form.Item>
          <Form.Item label="檢驗日期">
            <RangePicker
              value={filters.dateRange}
              onChange={(d) => setFilters({ ...filters, dateRange: d })}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">查詢</Button>
              <Button onClick={() => setFilters({ serial_number: '', lot_no: '', iqc_result: null, dateRange: null })}>清除</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card title="檢驗紀錄">
        <Table
          rowKey={(r) => r.id || `${r.serial_number}-${r.lot_no}`}
          columns={columns}
          dataSource={records}
          loading={loading}
          pagination={{ pageSize: 20 }}
        />
      </Card>
    </Space>
  );
};

export default PcbaIQC;
