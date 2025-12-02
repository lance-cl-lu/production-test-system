#!/usr/bin/env python3
"""
生產測試程式模擬器
模擬產線測試設備上傳測試資料到 FastAPI 後端
"""

import requests
import time
import random
import json
from datetime import datetime
from typing import Dict, Any
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

API_URL = os.getenv('API_URL', 'http://localhost:8000/api/test-records/')
DEVICE_ID = os.getenv('DEVICE_ID', 'TESTER_001')
TEST_STATION = os.getenv('TEST_STATION', 'STATION_A')


class ProductionTester:
    """生產測試器"""
    
    def __init__(self, device_id: str, test_station: str):
        self.device_id = device_id
        self.test_station = test_station
        self.serial_counter = 1000
        
    def generate_test_data(self) -> Dict[str, Any]:
        """生成模擬測試資料"""
        # 模擬測試參數
        voltage = round(random.uniform(4.8, 5.2), 2)  # 5V ±4%
        current = round(random.uniform(0.45, 0.55), 2)  # 0.5A ±10%
        temperature = round(random.uniform(20, 35), 1)  # 室溫
        
        # 判定測試結果（90% PASS率）
        voltage_ok = 4.9 <= voltage <= 5.1
        current_ok = 0.48 <= current <= 0.52
        temp_ok = temperature <= 32
        
        test_result = "PASS" if (voltage_ok and current_ok and temp_ok) else "FAIL"
        
        # 生成序號
        serial_number = f"SN{datetime.now().strftime('%Y%m%d')}{self.serial_counter:04d}"
        self.serial_counter += 1
        
        # 詳細測試數據
        test_details = {
            "voltage_spec": "5V ±2%",
            "current_spec": "0.5A ±4%",
            "temp_spec": "≤32°C",
            "voltage_ok": voltage_ok,
            "current_ok": current_ok,
            "temp_ok": temp_ok,
            "test_duration_ms": random.randint(1000, 3000),
        }
        
        return {
            "device_id": self.device_id,
            "product_name": random.choice([
                "產品型號A", "產品型號B", "產品型號C"
            ]),
            "serial_number": serial_number,
            "test_station": self.test_station,
            "test_result": test_result,
            "test_time": datetime.now().isoformat(),
            "test_data": json.dumps(test_details, ensure_ascii=False),
            "voltage": voltage,
            "current": current,
            "temperature": temperature,
        }
    
    def upload_test_result(self, test_data: Dict[str, Any]) -> bool:
        """上傳測試結果到 FastAPI"""
        try:
            response = requests.post(API_URL, json=test_data, timeout=5)
            
            if response.status_code == 201:
                print(f"✅ 上傳成功: {test_data['serial_number']} - {test_data['test_result']}")
                return True
            else:
                print(f"❌ 上傳失敗: HTTP {response.status_code}")
                print(f"   錯誤訊息: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 連線錯誤: {e}")
            return False
    
    def run_continuous_test(self, interval: float = 5.0):
        """連續執行測試（模擬產線運作）"""
        print(f"🔧 測試程式啟動")
        print(f"   設備ID: {self.device_id}")
        print(f"   測試站: {self.test_station}")
        print(f"   API URL: {API_URL}")
        print(f"   測試間隔: {interval} 秒")
        print("-" * 60)
        
        try:
            while True:
                # 生成測試資料
                test_data = self.generate_test_data()
                
                # 上傳測試結果
                self.upload_test_result(test_data)
                
                # 等待下一次測試
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n⏹️  測試程式已停止")


def run_single_test():
    """執行單次測試（用於測試）"""
    tester = ProductionTester(DEVICE_ID, TEST_STATION)
    test_data = tester.generate_test_data()
    
    print("生成測試資料:")
    print(json.dumps(test_data, indent=2, ensure_ascii=False))
    print("\n開始上傳...")
    
    tester.upload_test_result(test_data)


def run_batch_test(count: int = 10, interval: float = 1.0):
    """執行批次測試"""
    tester = ProductionTester(DEVICE_ID, TEST_STATION)
    
    print(f"🔄 執行批次測試 ({count} 筆)")
    print("-" * 60)
    
    for i in range(count):
        test_data = tester.generate_test_data()
        tester.upload_test_result(test_data)
        
        if i < count - 1:
            time.sleep(interval)
    
    print(f"\n✅ 批次測試完成，共上傳 {count} 筆資料")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        
        if mode == "single":
            # 單次測試
            run_single_test()
            
        elif mode == "batch":
            # 批次測試
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            run_batch_test(count)
            
        elif mode == "continuous":
            # 連續測試
            interval = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
            tester = ProductionTester(DEVICE_ID, TEST_STATION)
            tester.run_continuous_test(interval)
            
        else:
            print("使用方式:")
            print("  python tester.py single          - 執行單次測試")
            print("  python tester.py batch [數量]    - 執行批次測試")
            print("  python tester.py continuous [間隔] - 連續測試模式")
    else:
        # 預設執行連續測試
        tester = ProductionTester(DEVICE_ID, TEST_STATION)
        tester.run_continuous_test()
