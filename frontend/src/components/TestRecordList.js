import React, { useState, useEffect } from 'react';
import { Table, Tag, Space, Button, Input, DatePicker, Select, message } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { testRecordsAPI } from '../services/api';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;
const { Option } = Select;

const TestRecordList = ({ onNewRecord }) => {
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
      message.error('載入資料失敗');
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
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '序號',
      dataIndex: 'serial_number',
      key: 'serial_number',
    },
    {
      title: '產品名稱',
      dataIndex: 'product_name',
      key: 'product_name',
    },
    {
      title: '設備ID',
      dataIndex: 'device_id',
      key: 'device_id',
    },
    {
      title: '測試站別',
      dataIndex: 'test_station',
      key: 'test_station',
    },
    {
      title: '測試結果',
      dataIndex: 'test_result',
      key: 'test_result',
      render: (result) => (
        <Tag color={result === 'PASS' ? 'green' : 'red'}>
          {result}
        </Tag>
      ),
    },
    {
      title: '電壓 (V)',
      dataIndex: 'voltage',
      key: 'voltage',
      render: (val) => val?.toFixed(2) || '-',
    },
    {
      title: '電流 (A)',
      dataIndex: 'current',
      key: 'current',
      render: (val) => val?.toFixed(2) || '-',
    },
    {
      title: '溫度 (°C)',
      dataIndex: 'temperature',
      key: 'temperature',
      render: (val) => val?.toFixed(1) || '-',
    },
    {
      title: '測試時間',
      dataIndex: 'test_time',
      key: 'test_time',
      render: (time) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '雲端上傳',
      dataIndex: 'uploaded_to_cloud',
      key: 'uploaded_to_cloud',
      render: (uploaded) => (
        <Tag color={uploaded ? 'blue' : 'default'}>
          {uploaded ? '已上傳' : '未上傳'}
        </Tag>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="設備ID"
          value={filters.device_id}
          onChange={(e) => setFilters({ ...filters, device_id: e.target.value })}
          style={{ width: 200 }}
        />
        <Select
          placeholder="測試結果"
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
          查詢
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchRecords}
        >
          重新整理
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={records}
        rowKey="id"
        loading={loading}
        pagination={{
          pageSize: 20,
          showTotal: (total) => `共 ${total} 筆`,
        }}
      />
    </div>
  );
};

export default TestRecordList;
