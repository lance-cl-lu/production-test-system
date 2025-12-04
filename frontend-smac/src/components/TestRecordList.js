import React, { useState, useEffect } from 'react';
import { Table, Tag, Space, Button, Input, DatePicker, Select, message } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { testRecordsAPI } from '../services/api';
import { translations } from '../i18n/locales';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;
const { Option } = Select;

const TestRecordList = ({ onNewRecord, language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    device_id: '',
    test_result: null,
    dateRange: null,
  });

  const fetchRecords = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.device_id) params.device_id = filters.device_id;
      if (filters.test_result) params.test_result = filters.test_result;
      if (filters.dateRange) {
        params.start_date = filters.dateRange[0].toISOString();
        params.end_date = filters.dateRange[1].toISOString();
      }

      const response = await testRecordsAPI.getAll(params);
      setRecords(response.data);
    } catch (error) {
      message.error(t.loadDataFailed);
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  useEffect(() => {
    if (onNewRecord) {
      // 當收到新記錄時重新載入
      fetchRecords();
    }
  }, [onNewRecord]);

  const columns = [
    {
      title: t.id,
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: t.serialNumber,
      dataIndex: 'serial_number',
      key: 'serial_number',
    },
    {
      title: t.productName,
      dataIndex: 'product_name',
      key: 'product_name',
    },
    {
      title: t.deviceId,
      dataIndex: 'device_id',
      key: 'device_id',
    },
    {
      title: t.testStation,
      dataIndex: 'test_station',
      key: 'test_station',
    },
    {
      title: t.testResult,
      dataIndex: 'test_result',
      key: 'test_result',
      render: (result) => (
        <Tag color={result === 'PASS' ? 'green' : 'red'}>
          {result}
        </Tag>
      ),
    },
    {
      title: t.voltage,
      dataIndex: 'voltage',
      key: 'voltage',
      render: (val) => val?.toFixed(2) || '-',
    },
    {
      title: t.current,
      dataIndex: 'current',
      key: 'current',
      render: (val) => val?.toFixed(2) || '-',
    },
    {
      title: t.temperature,
      dataIndex: 'temperature',
      key: 'temperature',
      render: (val) => val?.toFixed(1) || '-',
    },
    {
      title: t.testTime,
      dataIndex: 'test_time',
      key: 'test_time',
      render: (time) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t.cloudUpload,
      dataIndex: 'uploaded_to_cloud',
      key: 'uploaded_to_cloud',
      render: (uploaded) => (
        <Tag color={uploaded ? 'blue' : 'default'}>
          {uploaded ? t.uploaded : t.notUploaded}
        </Tag>
      ),
    },
    {
      title: t.delete,
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button
          danger
          size="small"
          onClick={async () => {
            try {
              await testRecordsAPI.delete(record.id);
              message.success(t.deletedSuccess || 'Deleted');
              fetchRecords();
            } catch (err) {
              console.error(err);
              message.error(t.deletedFailed || 'Delete failed');
            }
          }}
        >
          {t.delete}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder={t.deviceIdPlaceholder}
          value={filters.device_id}
          onChange={(e) => setFilters({ ...filters, device_id: e.target.value })}
          style={{ width: 200 }}
        />
        <Select
          placeholder={t.testResultPlaceholder}
          value={filters.test_result}
          onChange={(value) => setFilters({ ...filters, test_result: value })}
          style={{ width: 120 }}
          allowClear
        >
          <Option value="PASS">PASS</Option>
          <Option value="FAIL">FAIL</Option>
        </Select>
        <RangePicker
          value={filters.dateRange}
          onChange={(dates) => setFilters({ ...filters, dateRange: dates })}
        />
        <Button
          type="primary"
          icon={<SearchOutlined />}
          onClick={fetchRecords}
        >
          {t.search}
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchRecords}
        >
          {t.refresh}
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={records}
        rowKey="id"
        loading={loading}
        pagination={{
          pageSize: 20,
          showTotal: (total) => `${t.total} ${total} ${t.items}`,
        }}
      />
    </div>
  );
};

export default TestRecordList;
