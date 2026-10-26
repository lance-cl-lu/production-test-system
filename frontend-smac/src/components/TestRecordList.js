import React, { useCallback, useEffect, useState } from 'react';
import { Button, DatePicker, Input, message, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { DeleteOutlined, DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { testRecordsAPI } from '../services/api';
import { translations } from '../i18n/locales';

const { RangePicker } = DatePicker;
const resultTag = (result, t) => {
  const normalized = String(result || '').toLowerCase();
  const color = normalized === 'pass' ? 'green' : normalized === 'fail' ? 'red' : 'default';
  const labels = {
    pass: t?.sensorIQC?.passed || 'PASS',
    fail: t?.sensorIQC?.failed || 'FAIL',
    pending: t?.pendingTests || 'PENDING',
  };
  return <Tag color={color}>{normalized ? labels[normalized] || normalized.toUpperCase() : '-'}</Tag>;
};
const numberValue = (value, digits = 2) =>
  value === null || value === undefined ? '-' : Number(value).toFixed(digits);
const taipeiDateTime = (value, language = 'zh-TW') => value ? new Intl.DateTimeFormat(
  language === 'vi' ? 'vi-VN' : language === 'en' ? 'en-US' : 'zh-TW', {
  timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
}).format(new Date(value)).replaceAll('/', '-') : '-';

const RecordFilters = ({ filters, setFilters, onSearch, onExport, onDeleteUploaded, loading, exporting, deleting, t, serialPlaceholder }) => (
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
    <Button icon={<DownloadOutlined />} onClick={onExport} loading={exporting}>
      {t.exportCsv}
    </Button>
    <Button danger icon={<DeleteOutlined />} onClick={onDeleteUploaded} loading={deleting}>
      {t.deleteUploadedRecords}
    </Button>
  </Space>
);

const SensorRunList = ({ refreshTrigger, t, language }) => {
  const [records, setRecords] = useState([]);
  const [flashRecords, setFlashRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
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
      const flashResponse = await testRecordsAPI.getFirmwareFlashRecords();
      setFlashRecords(flashResponse.data);
    } catch (error) {
      console.error(error);
      message.error(t.loadDataFailed);
    } finally {
      setLoading(false);
    }
  }, [filters, t.loadDataFailed]);

  useEffect(() => { fetchRecords(); }, [fetchRecords, refreshTrigger]);

  const filterParams = useCallback(() => {
    const params = {};
    if (filters.serial.trim()) params.serial_wle = filters.serial.trim();
    if (filters.test_result) params.test_result = filters.test_result;
    if (filters.dateRange) {
      params.start_date = filters.dateRange[0].startOf('day').toISOString();
      params.end_date = filters.dateRange[1].endOf('day').toISOString();
    }
    return params;
  }, [filters]);

  const exportCsv = async () => {
    setExporting(true);
    try {
      const exportLanguage = language === 'en' ? 'en-US' : language;
      const response = await testRecordsAPI.exportSensorTestRuns({
        ...filterParams(), language: exportLanguage,
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `sensor_test_records_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success(t.exportSuccess);
    } catch (error) {
      console.error(error);
      message.error(t.exportFailed);
    } finally {
      setExporting(false);
    }
  };

  const deleteUploadedRecords = () => Modal.confirm({
    title: t.deleteUploadedRecords,
    content: t.deleteUploadedRecordsConfirm,
    okText: t.delete,
    okButtonProps: { danger: true, loading: deleting },
    cancelText: t.cancel,
    onOk: async () => {
      setDeleting(true);
      try {
        const { data } = await testRecordsAPI.deleteUploadedSensorTestRuns();
        message.success(t.deleteUploadedRecordsSuccess.replace('{count}', String(data.deleted_count)));
        await fetchRecords();
      } catch (error) {
        console.error(error);
        message.error(t.deleteUploadedRecordsFailed);
      } finally {
        setDeleting(false);
      }
    },
  });

  const sensorDetailStages = ['sht41', 'ens210', 'lps22df', 'bme690'];
  const flashDataForRun = (run) => {
    const paired = flashRecords.find((record) => !record.mcu_type &&
      record.serial_wle === run.serial_wle && record.serial_wba === run.serial_wba);
    const wle = flashRecords.find((record) => record.mcu_type === 'WLE' &&
      record.serial_wle === run.serial_wle);
    const wba = flashRecords.find((record) => record.mcu_type === 'WBA' &&
      record.serial_wba === run.serial_wba);
    const sources = [paired, wle, wba].filter(Boolean);
    const latest = [...sources].sort((a, b) =>
      new Date(b.updated_at || 0) - new Date(a.updated_at || 0))[0];
    return {
      wleTest: (paired?.test_firmware_count || 0) + (wle?.test_firmware_count || 0),
      wbaTest: (paired?.test_firmware_count || 0) + (wba?.test_firmware_count || 0),
      wleDiagnostics: (paired?.diagnostics_firmware_count || 0) + (wle?.diagnostics_firmware_count || 0),
      wbaDiagnostics: (paired?.diagnostics_firmware_count || 0) + (wba?.diagnostics_firmware_count || 0),
      diagnosticsNumber: latest?.diagnostics_number,
      updatedAt: latest?.updated_at,
    };
  };
  const sensorStages = [
    'getSensorIC', 'sht41', 'ens210', 'lps22df', 'bme690',
    'testButton', 'testGreenLED', 'testOrangeLED', 'testBuzzer', 'testSPI',
  ];
  const stageResult = (record, stage) =>
    (record.items || []).find((item) => item.stage === stage)?.status;

  const sensorDetailColumns = [
    { title: t.stage, dataIndex: 'stage', width: 140,
      render: (stage) => t.sensorIQC?.[stage] || stage },
    { title: t.testResult, dataIndex: 'status', width: 100,
      render: (value) => resultTag(value, t) },
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
    { title: t.testResult, dataIndex: 'test_result', fixed: 'left', width: 110,
      align: 'center', render: (value) => resultTag(value, t) },
    { title: t.testTime, dataIndex: 'started_at', width: 170,
      render: (value) => taipeiDateTime(value, language) },
    { title: t.wleTestFirmwareFlash, key: 'wle_test_firmware_count', align: 'right', width: 190,
      render: (_, record) => flashDataForRun(record).wleTest },
    { title: t.wbaTestFirmwareFlash, key: 'wba_test_firmware_count', align: 'right', width: 190,
      render: (_, record) => flashDataForRun(record).wbaTest },
    { title: t.wleDiagnosticsFirmwareFlash, key: 'wle_diagnostics_firmware_count', align: 'right', width: 220,
      render: (_, record) => flashDataForRun(record).wleDiagnostics },
    { title: t.wbaDiagnosticsFirmwareFlash, key: 'wba_diagnostics_firmware_count', align: 'right', width: 220,
      render: (_, record) => flashDataForRun(record).wbaDiagnostics },
    { title: t.diagnosticsSerialNumber, key: 'diagnostics_number', width: 200,
      render: (_, record) => flashDataForRun(record).diagnosticsNumber || '-' },
    { title: t.firmwareFlashTime, key: 'firmware_flash_time', width: 190,
      render: (_, record) => taipeiDateTime(flashDataForRun(record).updatedAt, language) },
    ...sensorStages.map((stage) => ({
      title: t.sensorIQC?.[stage] || stage,
      key: stage,
      width: 135,
      align: 'center',
      render: (_, record) => resultTag(stageResult(record, stage), t),
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
      onExport={exportCsv} onDeleteUploaded={deleteUploadedRecords}
      loading={loading} exporting={exporting} deleting={deleting}
      t={t} serialPlaceholder={t.serialWle} />
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
      scroll={{ x: 3250 }}
      pagination={{ pageSize: 10, showTotal: (total) => `${t.total} ${total} ${t.items}` }}
    />
  </>;
};

const TestRecordList = ({ onNewRecord, language = 'zh-TW' }) => {
  const t = translations[language];
  return <>
    <Typography.Title level={4}>{t.sensorRuns}</Typography.Title>
    <SensorRunList refreshTrigger={onNewRecord} t={t} language={language} />
  </>;
};

export default TestRecordList;
