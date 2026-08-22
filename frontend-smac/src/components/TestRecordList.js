import React, { useCallback, useEffect, useState } from 'react';
import { Button, DatePicker, Input, message, Select, Space, Table, Tabs, Tag } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { testRecordsAPI } from '../services/api';
import { translations } from '../i18n/locales';

const { RangePicker } = DatePicker;
const resultTag = (result) => {
  const normalized = String(result || '').toLowerCase();
  const color = normalized === 'pass' ? 'green' : normalized === 'fail' ? 'red' : 'default';
  return <Tag color={color}>{normalized ? normalized.toUpperCase() : '-'}</Tag>;
};
const numberValue = (value, digits = 2) =>
  value === null || value === undefined ? '-' : Number(value).toFixed(digits);

const RecordFilters = ({ filters, setFilters, onSearch, loading, t, serialPlaceholder }) => (
  <Space style={{ marginBottom: 16 }} wrap>
    <Input
      placeholder={serialPlaceholder}
      value={filters.serial}
      onChange={(event) => setFilters({ ...filters, serial: event.target.value })}
      style={{ width: 240 }}
      allowClear
    />
    <Select
      placeholder={t.testResultPlaceholder}
      value={filters.test_result}
      onChange={(value) => setFilters({ ...filters, test_result: value })}
      style={{ width: 130 }}
      options={[{ value: 'PASS', label: 'PASS' }, { value: 'FAIL', label: 'FAIL' }]}
      allowClear
    />
    <RangePicker
      value={filters.dateRange}
      onChange={(dateRange) => setFilters({ ...filters, dateRange })}
    />
    <Button type="primary" icon={<SearchOutlined />} onClick={onSearch} loading={loading}>
      {t.search}
    </Button>
    <Button icon={<ReloadOutlined />} onClick={onSearch} loading={loading}>
      {t.refresh}
    </Button>
  </Space>
);

const SensorRunList = ({ refreshTrigger, t }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ serial: '', test_result: null, dateRange: null });

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.serial.trim()) params.serial_wle = filters.serial.trim();
      if (filters.test_result) params.test_result = filters.test_result;
      if (filters.dateRange) {
        params.start_date = filters.dateRange[0].startOf('day').toISOString();
        params.end_date = filters.dateRange[1].endOf('day').toISOString();
      }
      const response = await testRecordsAPI.getSensorTestRuns(params);
      setRecords(response.data);
    } catch (error) {
      console.error(error);
      message.error(t.loadDataFailed);
    } finally {
      setLoading(false);
    }
  }, [filters, t.loadDataFailed]);

  useEffect(() => { fetchRecords(); }, [fetchRecords, refreshTrigger]);

  const sensorDetailStages = ['sht41', 'ens210', 'lps22df', 'bme690'];
  const sensorStages = [
    'getSensorIC', 'sht41', 'ens210', 'lps22df', 'bme690',
    'testButton', 'testGreenLED', 'testOrangeLED', 'testBuzzer', 'testSPI',
  ];
  const stageResult = (record, stage) =>
    (record.items || []).find((item) => item.stage === stage)?.status;

  const sensorDetailColumns = [
    { title: t.stage, dataIndex: 'stage', width: 140,
      render: (stage) => t.sensorIQC?.[stage] || stage },
    { title: t.testResult, dataIndex: 'status', width: 100, render: resultTag },
    { title: t.temperature, dataIndex: 'temperature_c',
      render: (value) => numberValue(value) },
    { title: t.humidity, dataIndex: 'humidity_percent',
      render: (value) => numberValue(value) },
    { title: t.pressure, dataIndex: 'pressure_hpa',
      render: (value) => numberValue(value) },
    { title: t.gasResistance, dataIndex: 'gas_resistance_ohm',
      render: (value) => numberValue(value) },
  ];

  const sensorDetails = (record) => sensorDetailStages.map((stage) => ({
    stage,
    ...((record.items || []).find((item) => item.stage === stage) || {}),
  }));

  const columns = [
    { title: t.serialWle, dataIndex: 'serial_wle', fixed: 'left', width: 180 },
    { title: t.serialWba, dataIndex: 'serial_wba', fixed: 'left', width: 180,
      render: (value) => value || '-' },
    { title: t.testTime, dataIndex: 'started_at', width: 170,
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
    ...sensorStages.map((stage) => ({
      title: t.sensorIQC?.[stage] || stage,
      key: stage,
      width: 135,
      align: 'center',
      render: (_, record) => resultTag(stageResult(record, stage)),
    })),
    {
      title: t.delete,
      width: 90,
      fixed: 'right',
      render: (_, record) => (
        <Button danger size="small" onClick={async () => {
          try {
            await testRecordsAPI.deleteSensorTestRun(record.id);
            message.success(t.deletedSuccess);
            fetchRecords();
          } catch (error) {
            console.error(error);
            message.error(t.deletedFailed);
          }
        }}>
          {t.delete}
        </Button>
      ),
    },
  ];

  return <>
    <RecordFilters filters={filters} setFilters={setFilters} onSearch={fetchRecords}
      loading={loading} t={t} serialPlaceholder={t.serialWle} />
    <Table
      columns={columns}
      dataSource={records}
      rowKey="id"
      loading={loading}
      expandable={{
        expandedRowRender: (record) => (
          <Table
            columns={sensorDetailColumns}
            dataSource={sensorDetails(record)}
            rowKey="stage"
            pagination={false}
            size="small"
          />
        ),
      }}
      scroll={{ x: 2100 }}
      pagination={{ pageSize: 10, showTotal: (total) => `${t.total} ${total} ${t.items}` }}
    />
  </>;
};

const LegacyRecordList = ({ refreshTrigger, t }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ serial: '', test_result: null, dateRange: null });

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.serial.trim()) params.device_id = filters.serial.trim();
      if (filters.test_result) params.test_result = filters.test_result;
      if (filters.dateRange) {
        params.start_date = filters.dateRange[0].startOf('day').toISOString();
        params.end_date = filters.dateRange[1].endOf('day').toISOString();
      }
      const response = await testRecordsAPI.getAll(params);
      setRecords(response.data);
    } catch (error) {
      console.error(error);
      message.error(t.loadDataFailed);
    } finally {
      setLoading(false);
    }
  }, [filters, t.loadDataFailed]);

  useEffect(() => { fetchRecords(); }, [fetchRecords, refreshTrigger]);

  const columns = [
    { title: t.id, dataIndex: 'id', width: 70 },
    { title: t.serialNumber, dataIndex: 'serial_number' },
    { title: t.productName, dataIndex: 'product_name' },
    { title: t.deviceId, dataIndex: 'device_id' },
    { title: t.testStation, dataIndex: 'test_station' },
    { title: t.testResult, dataIndex: 'test_result', render: resultTag },
    { title: t.voltage, dataIndex: 'voltage', render: (value) => numberValue(value) },
    { title: t.current, dataIndex: 'current', render: (value) => numberValue(value) },
    { title: t.temperature, dataIndex: 'temperature', render: (value) => numberValue(value, 1) },
    { title: t.testTime, dataIndex: 'test_time', render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
  ];

  return <>
    <RecordFilters filters={filters} setFilters={setFilters} onSearch={fetchRecords}
      loading={loading} t={t} serialPlaceholder={t.deviceIdPlaceholder} />
    <Table columns={columns} dataSource={records} rowKey="id" loading={loading}
      pagination={{ pageSize: 10, showTotal: (total) => `${t.total} ${total} ${t.items}` }} />
  </>;
};

const TestRecordList = ({ onNewRecord, language = 'zh-TW' }) => {
  const t = translations[language];
  return <Tabs defaultActiveKey="sensor" items={[
    { key: 'sensor', label: t.sensorRuns, children: <SensorRunList refreshTrigger={onNewRecord} t={t} /> },
    { key: 'legacy', label: t.legacyRecords, children: <LegacyRecordList refreshTrigger={onNewRecord} t={t} /> },
  ]} />;
};

export default TestRecordList;
