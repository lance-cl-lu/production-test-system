import React, { useState, useEffect, useCallback } from 'react';
import { Table, Tag, Space, Button, Input, DatePicker, Select, message } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import axios from 'axios';
import { translations } from '../i18n/locales';

const { RangePicker } = DatePicker;
const { Option } = Select;

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

const TestRecordList = ({ onNewRecord, language = 'zh-TW' }) => {
  const t = translations[language];
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ device_id: '', test_result: null, dateRange: null });

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.device_id) params.device_id = filters.device_id;
      if (filters.test_result) params.test_result = filters.test_result;
      if (filters.dateRange) {
        params.start_date = filters.dateRange[0].toISOString();
        params.end_date = filters.dateRange[1].toISOString();
      }
      const res = await axios.get(`${API_BASE}/api/test-records/`, { params });
      setRecords(res.data || []);
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || '';
      message.error(`${t.loadDataFailed}${detail ? `: ${detail}` : ''}`);
    } finally {
      setLoading(false);
    }
  }, [filters.device_id, filters.test_result, filters.dateRange, t.loadDataFailed]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);
  useEffect(() => { if (onNewRecord) fetchRecords(); }, [onNewRecord, fetchRecords]);

  const columns = [
    { title: t.id, dataIndex: 'id', key: 'id', width: 80 },
    { title: t.serialNumber, dataIndex: 'serial_number', key: 'serial_number' },
    { title: t.productName, dataIndex: 'product_name', key: 'product_name' },
    { title: t.deviceId, dataIndex: 'device_id', key: 'device_id' },
    { title: t.testStation, dataIndex: 'test_station', key: 'test_station' },
    { title: t.testResult, dataIndex: 'test_result', key: 'test_result', render: (r) => <Tag color={r === 'PASS' ? 'green' : 'red'}>{r}</Tag> },
    { title: t.voltage, dataIndex: 'voltage', key: 'voltage', render: (v) => v?.toFixed(2) || '-' },
    { title: t.current, dataIndex: 'current', key: 'current', render: (v) => v?.toFixed(2) || '-' },
    { title: t.temperature, dataIndex: 'temperature', key: 'temperature', render: (v) => v?.toFixed(1) || '-' },
    { title: t.testTime, dataIndex: 'test_time', key: 'test_time', render: (time) => dayjs(time).format('YYYY-MM-DD HH:mm:ss') },
    { title: t.cloudUpload, dataIndex: 'uploaded_to_cloud', key: 'uploaded_to_cloud', render: (u) => <Tag color={u ? 'blue' : 'default'}>{u ? t.uploaded : t.notUploaded}</Tag> },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input placeholder={t.deviceIdPlaceholder} value={filters.device_id} onChange={(e) => setFilters({ ...filters, device_id: e.target.value })} style={{ width: 200 }} />
        <Select placeholder={t.testResultPlaceholder} value={filters.test_result} onChange={(v) => setFilters({ ...filters, test_result: v })} style={{ width: 120 }} allowClear>
          <Option value="PASS">PASS</Option>
          <Option value="FAIL">FAIL</Option>
        </Select>
        <RangePicker value={filters.dateRange} onChange={(d) => setFilters({ ...filters, dateRange: d })} />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchRecords}>{t.search}</Button>
        <Button icon={<ReloadOutlined />} onClick={fetchRecords}>{t.refresh}</Button>
      </Space>
      <Table columns={columns} dataSource={records} rowKey="id" loading={loading} pagination={{ pageSize: 20, showTotal: (total) => `${t.total} ${total} ${t.items}` }} />
    </div>
  );
};

export default TestRecordList;
