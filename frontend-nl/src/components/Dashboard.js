import React, { useState, useEffect } from 'react';
import { Card, Statistic, Row, Col } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import axios from 'axios';
import { translations } from '../i18n/locales';

// 簡化版儀表板（可後續擴充）
const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

const Dashboard = ({ language = 'zh-TW' }) => {
  const [stats, setStats] = useState({ total: 0, passed: 0, failed: 0 });
  const t = translations[language];

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/test-records/`, { params: { limit: 500 } });
        const records = response.data || [];
        setStats({
          total: records.length,
          passed: records.filter((r) => r.test_result === 'PASS').length,
          failed: records.filter((r) => r.test_result === 'FAIL').length,
        });
      } catch (e) {}
    };
    fetchStats();
  }, []);

  const passRate = stats.total ? ((stats.passed / stats.total) * 100).toFixed(1) : 0;

  return (
    <Row gutter={16}>
      <Col span={8}>
        <Card>
          <Statistic title={t.totalTests} value={stats.total} prefix={<ClockCircleOutlined />} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title={t.passedTests} value={stats.passed} valueStyle={{ color: '#3f8600' }} prefix={<CheckCircleOutlined />} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title={t.failedTests} value={stats.failed} valueStyle={{ color: '#cf1322' }} prefix={<CloseCircleOutlined />} />
        </Card>
      </Col>
      <Col span={24} style={{ marginTop: 16 }}>
        <Card>
          <Statistic title={t.passRate} value={passRate} suffix="%" valueStyle={{ color: passRate >= 90 ? '#3f8600' : '#cf1322' }} />
        </Card>
      </Col>
    </Row>
  );
};

export default Dashboard;
