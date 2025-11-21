import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from curl_cffi import requests
import json
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct
import secrets
import string
import threading
import time

class VDEXTrader:
    def __init__(self, root):
        self.root = root
        self.root.title("VDEX Trader")
        self.root.geometry("1000x1000")

        self.access_token = None
        self.refresh_token = None
        self.last_message = None
        self.last_chain_id = None
        self.current_positions = []
        self.auto_trading = False
        self.auto_thread = None

        self.base_url = "https://api.vdex.trade"
        self.login_url = f"{self.base_url}/auth-service/api/v2/auth/login"
        self.balance_url = f"{self.base_url}/api-gateway/v1/user/balance"
        self.positions_url = f"{self.base_url}/api-gateway/v2/users/positions"
        self.price_url = f"{self.base_url}/api-gateway/v1/tokens/cmc-price"
        self.order_url = f"{self.base_url}/api-gateway/v2/orders"
        self.liquidate_url = f"{self.base_url}/api-gateway/v2/orders/liquidate"

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        login_frame = ttk.LabelFrame(main_frame, text="로그인", padding="10")
        login_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(login_frame, text="지갑 주소:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.address_entry = ttk.Entry(login_frame, width=50)
        self.address_entry.grid(row=0, column=1, pady=2, padx=5)

        ttk.Label(login_frame, text="개인키:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.privkey_entry = ttk.Entry(login_frame, width=50, show="*")
        self.privkey_entry.grid(row=1, column=1, pady=2, padx=5)

        ttk.Button(login_frame, text="Nonce 생성 & 서명", command=self.get_nonce_and_sign).grid(row=2, column=0, columnspan=2, pady=5)

        ttk.Label(login_frame, text="서명:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.signature_entry = ttk.Entry(login_frame, width=50)
        self.signature_entry.grid(row=3, column=1, pady=2, padx=5)

        button_frame = ttk.Frame(login_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="로그인", command=self.login, width=20).pack()

        self.status_label = ttk.Label(login_frame, text="로그인 필요", foreground="red")
        self.status_label.grid(row=5, column=0, columnspan=2)

        balance_frame = ttk.LabelFrame(main_frame, text="잔고", padding="10")
        balance_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5, padx=(0, 5))

        self.balance_text = scrolledtext.ScrolledText(balance_frame, width=40, height=10, wrap=tk.WORD)
        self.balance_text.pack(fill=tk.BOTH, expand=True)

        ttk.Button(balance_frame, text="잔고 새로고침", command=self.get_balance).pack(pady=5)

        position_frame = ttk.LabelFrame(main_frame, text="포지션", padding="10")
        position_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        self.position_text = scrolledtext.ScrolledText(position_frame, width=40, height=10, wrap=tk.WORD)
        self.position_text.pack(fill=tk.BOTH, expand=True)

        position_button_frame = ttk.Frame(position_frame)
        position_button_frame.pack(fill=tk.X, pady=5)

        ttk.Button(position_button_frame, text="포지션 새로고침", command=self.get_positions).pack(side=tk.LEFT, padx=2)
        ttk.Button(position_button_frame, text="모든 포지션 청산", command=self.liquidate_all_positions).pack(side=tk.LEFT, padx=2)

        order_frame = ttk.LabelFrame(main_frame, text="주문", padding="10")
        order_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        order_input_frame = ttk.Frame(order_frame)
        order_input_frame.pack(fill=tk.X, pady=5)

        ttk.Label(order_input_frame, text="심볼:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.symbol_entry = ttk.Entry(order_input_frame, width=10)
        self.symbol_entry.grid(row=0, column=1, padx=5)
        self.symbol_entry.insert(0, "ETH")

        ttk.Label(order_input_frame, text="방향:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.direction_var = tk.StringVar(value="buy")
        ttk.Radiobutton(order_input_frame, text="매수", variable=self.direction_var, value="buy").grid(row=0, column=3, padx=5)
        ttk.Radiobutton(order_input_frame, text="매도", variable=self.direction_var, value="sell").grid(row=0, column=4, padx=5)

        ttk.Label(order_input_frame, text="수량(USD):").grid(row=0, column=5, sticky=tk.W, padx=5)
        self.quantity_entry = ttk.Entry(order_input_frame, width=10)
        self.quantity_entry.grid(row=0, column=6, padx=5)
        self.quantity_entry.insert(0, "10")

        ttk.Label(order_input_frame, text="레버리지:").grid(row=0, column=7, sticky=tk.W, padx=5)
        self.leverage_entry = ttk.Entry(order_input_frame, width=5)
        self.leverage_entry.grid(row=0, column=8, padx=5)
        self.leverage_entry.insert(0, "1")

        order_button_frame = ttk.Frame(order_frame)
        order_button_frame.pack(fill=tk.X, pady=5)

        self.current_price_label = ttk.Label(order_button_frame, text="현재가: -")
        self.current_price_label.pack(side=tk.LEFT, padx=10)

        ttk.Button(order_button_frame, text="현재가 조회", command=self.get_price).pack(side=tk.LEFT, padx=5)
        ttk.Button(order_button_frame, text="마켓 주문", command=self.place_market_order).pack(side=tk.LEFT, padx=5)
        ttk.Button(order_button_frame, text="오픈 오더 조회", command=self.get_open_orders).pack(side=tk.LEFT, padx=5)

        self.orders_text = scrolledtext.ScrolledText(order_frame, width=80, height=6, wrap=tk.WORD)
        self.orders_text.pack(fill=tk.BOTH, expand=True, pady=5)

        auto_frame = ttk.LabelFrame(main_frame, text="자동 반복 거래", padding="10")
        auto_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        auto_settings_frame = ttk.Frame(auto_frame)
        auto_settings_frame.pack(fill=tk.X, pady=5)

        ttk.Label(auto_settings_frame, text="반복 횟수:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.repeat_count_entry = ttk.Entry(auto_settings_frame, width=10)
        self.repeat_count_entry.grid(row=0, column=1, padx=5)
        self.repeat_count_entry.insert(0, "10")

        ttk.Label(auto_settings_frame, text="대기 시간(초):").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.wait_time_entry = ttk.Entry(auto_settings_frame, width=10)
        self.wait_time_entry.grid(row=0, column=3, padx=5)
        self.wait_time_entry.insert(0, "60")

        ttk.Label(auto_settings_frame, text="심볼:").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.auto_symbol_entry = ttk.Entry(auto_settings_frame, width=10)
        self.auto_symbol_entry.grid(row=0, column=5, padx=5)
        self.auto_symbol_entry.insert(0, "ETH")

        ttk.Label(auto_settings_frame, text="방향:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.auto_direction_var = tk.StringVar(value="buy")
        ttk.Radiobutton(auto_settings_frame, text="매수", variable=self.auto_direction_var, value="buy").grid(row=1, column=1, padx=5)
        ttk.Radiobutton(auto_settings_frame, text="매도", variable=self.auto_direction_var, value="sell").grid(row=1, column=2, padx=5)

        ttk.Label(auto_settings_frame, text="수량(USD):").grid(row=1, column=3, sticky=tk.W, padx=5)
        self.auto_quantity_entry = ttk.Entry(auto_settings_frame, width=10)
        self.auto_quantity_entry.grid(row=1, column=4, padx=5)
        self.auto_quantity_entry.insert(0, "10")

        ttk.Label(auto_settings_frame, text="레버리지:").grid(row=1, column=5, sticky=tk.W, padx=5)
        self.auto_leverage_entry = ttk.Entry(auto_settings_frame, width=5)
        self.auto_leverage_entry.grid(row=1, column=6, padx=5)
        self.auto_leverage_entry.insert(0, "1")

        auto_control_frame = ttk.Frame(auto_frame)
        auto_control_frame.pack(fill=tk.X, pady=5)

        self.start_auto_btn = ttk.Button(auto_control_frame, text="자동 거래 시작", command=self.start_auto_trading)
        self.start_auto_btn.pack(side=tk.LEFT, padx=5)

        self.stop_auto_btn = ttk.Button(auto_control_frame, text="자동 거래 중지", command=self.stop_auto_trading, state=tk.DISABLED)
        self.stop_auto_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(auto_control_frame, text="즉시 청산", command=self.quick_liquidate).pack(side=tk.LEFT, padx=5)

        self.auto_status_label = ttk.Label(auto_control_frame, text="대기 중", foreground="gray")
        self.auto_status_label.pack(side=tk.LEFT, padx=10)

        self.auto_log_text = scrolledtext.ScrolledText(auto_frame, width=80, height=5, wrap=tk.WORD)
        self.auto_log_text.pack(fill=tk.BOTH, expand=True, pady=5)

        log_frame = ttk.LabelFrame(main_frame, text="로그", padding="10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, width=80, height=6, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=0)
        main_frame.rowconfigure(3, weight=0)
        main_frame.rowconfigure(4, weight=0)

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        print(message)

    def auto_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.auto_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.auto_log_text.see(tk.END)
        self.log(message)

    def get_nonce_and_sign(self):
        address = self.address_entry.get().strip()
        privkey = self.privkey_entry.get().strip()

        if not address:
            messagebox.showerror("오류", "지갑 주소를 입력해주세요.")
            return

        if not privkey:
            messagebox.showwarning("안내", "개인키가 없습니다. 메시지를 생성합니다.\n직접 MetaMask에서 서명해서 입력하세요.")

        try:
            nonce = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(17))
            issued_at = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            chain_id = 56

            if privkey:
                if not privkey.startswith('0x'):
                    privkey = '0x' + privkey
                account = Account.from_key(privkey)
                address = account.address
                self.address_entry.delete(0, tk.END)
                self.address_entry.insert(0, address)

            message = f"""app.vdex.trade wants you to sign in with your Ethereum account:
{address}

Sign in with Ethereum to the app.

URI: https://app.vdex.trade
Version: 1
Chain ID: {chain_id}
Nonce: {nonce}
Issued At: {issued_at}"""

            self.last_message = message
            self.last_chain_id = chain_id

            self.log(f"Nonce 생성: {nonce}")
            self.log(f"생성된 메시지:\n{message}")

            if privkey:
                try:
                    message_hash = encode_defunct(text=message)
                    signed = account.sign_message(message_hash)
                    signature = signed.signature.hex()

                    if not signature.startswith('0x'):
                        signature = '0x' + signature

                    self.signature_entry.delete(0, tk.END)
                    self.signature_entry.insert(0, signature)

                    self.log("서명 생성 완료!")
                    messagebox.showinfo("성공", "서명이 생성되었습니다!\n이제 '로그인' 버튼을 클릭하세요.")
                except Exception as e:
                    messagebox.showerror("서명 오류", f"서명 생성 실패: {str(e)}")
                    self.log(f"서명 오류: {str(e)}")
            else:
                messagebox.showinfo("안내",
                    f"MetaMask에서 아래 메시지에 서명하세요:\n\n{message[:200]}...\n\n"
                    "서명값을 '서명' 필드에 붙여넣으세요.")
        except Exception as e:
            messagebox.showerror("오류", str(e))
            self.log(f"오류: {str(e)}")

    def login(self):
        address = self.address_entry.get().strip()
        signature = self.signature_entry.get().strip()

        if not address or not signature:
            messagebox.showerror("오류", "지갑 주소와 서명을 입력해주세요.")
            return

        if self.last_message and self.last_chain_id:
            message = self.last_message
            chain_id = self.last_chain_id
            self.log("저장된 메시지와 Chain ID 사용")
        else:
            messagebox.showwarning("경고", "먼저 'Nonce 생성 & 서명' 버튼을 눌러주세요!")
            return

        payload = {
            "address": address,
            "signature": signature,
            "message": message,
            "referrerCode": "KnightGravity5370",
            "chainId": chain_id
        }

        headers = {
            "accept": "application/json",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        try:
            self.log("로그인 시도 중...")
            response = requests.post(self.login_url, json=payload, headers=headers, impersonate="chrome120")

            self.log(f"응답 상태 코드: {response.status_code}")
            self.log(f"응답 내용: {response.text[:500]}")

            data = response.json()

            if data.get("code") == 0:
                self.access_token = data["data"]["accessToken"]
                self.refresh_token = data["data"]["refreshToken"]
                self.status_label.config(text="로그인 성공!", foreground="green")
                self.log("로그인 성공!")

                self.get_balance()
                self.get_positions()
                self.get_open_orders()
            else:
                messagebox.showerror("로그인 실패", data.get("message", "알 수 없는 오류"))
                self.log(f"로그인 실패: {data.get('message')}")
        except Exception as e:
            messagebox.showerror("오류", str(e))
            self.log(f"오류: {str(e)}")

    def get_balance(self):
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        headers = {
            "accept": "application/json",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "authorization": f"Bearer {self.access_token}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        try:
            self.log("잔고 조회 중...")
            response = requests.get(self.balance_url, headers=headers, impersonate="chrome120")

            data = response.json()
            self.balance_text.delete(1.0, tk.END)

            if data.get("code") == 0:
                balances = data.get("data", [])

                if balances:
                    for balance in balances:
                        token = balance.get("token_name", "Unknown")
                        total = balance.get("balance", 0)
                        available = balance.get("available", 0)
                        margin = balance.get("position_margins", 0)
                        unrealized = balance.get("unrealized_pnl", 0)

                        self.balance_text.insert(tk.END, f"토큰: {token}\n")
                        self.balance_text.insert(tk.END, f"총 잔고: {total}\n")
                        self.balance_text.insert(tk.END, f"사용 가능: {available}\n")
                        self.balance_text.insert(tk.END, f"포지션 마진: {margin}\n")
                        self.balance_text.insert(tk.END, f"미실현 손익: {unrealized}\n")
                        self.balance_text.insert(tk.END, f"{'-'*40}\n")

                    self.log("잔고 조회 완료")
                else:
                    self.balance_text.insert(tk.END, "잔고 없음\n")
                    self.log("잔고 없음")
            else:
                self.balance_text.insert(tk.END, f"오류: {data.get('message')}\n")
                self.log(f"잔고 조회 실패: {data.get('message')}")
        except Exception as e:
            self.balance_text.insert(tk.END, f"오류: {str(e)}\n")
            self.log(f"오류: {str(e)}")

    def get_positions(self):
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        headers = {
            "accept": "application/json",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "authorization": f"Bearer {self.access_token}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        try:
            self.log("포지션 조회 중...")
            response = requests.get(self.positions_url, headers=headers, impersonate="chrome120")

            data = response.json()
            self.position_text.delete(1.0, tk.END)

            if data.get("code") == 0:
                positions = data.get("data")

                if positions and isinstance(positions, list):
                    self.current_positions = positions
                else:
                    self.current_positions = []

                if positions:
                    if isinstance(positions, list):
                        self.position_text.insert(tk.END, f"총 {len(positions)}개의 포지션\n")
                        self.position_text.insert(tk.END, f"{'-'*40}\n")

                        for pos in positions:
                            token_id = pos.get("token_id", pos.get("base_asset_id", "Unknown"))
                            amount = pos.get("amount", 0)
                            direction_code = pos.get("direction", "")
                            direction = "롱(매수)" if direction_code == "buy" else "숏(매도)"
                            entry_price = pos.get("entry_price", 0)
                            mark_price = pos.get("mark_price", 0)
                            if direction_code == "buy":
                                unrealized_pnl = (mark_price - entry_price) * amount
                            else:
                                unrealized_pnl = (entry_price - mark_price) * amount
                            leverage = pos.get("leverage_factor", 1)

                            self.position_text.insert(tk.END, f"심볼: {token_id}\n")
                            self.position_text.insert(tk.END, f"방향: {direction}\n")
                            self.position_text.insert(tk.END, f"수량: {abs(amount):.6f}\n")
                            self.position_text.insert(tk.END, f"진입가: ${entry_price:.2f}\n")
                            self.position_text.insert(tk.END, f"현재가: ${mark_price:.2f}\n")
                            self.position_text.insert(tk.END, f"손익: ${unrealized_pnl:.2f}\n")
                            self.position_text.insert(tk.END, f"레버리지: {leverage}x\n")
                            self.position_text.insert(tk.END, f"{'-'*40}\n")

                        self.log(f"포지션 {len(positions)}개 조회 완료")
                    else:
                        self.position_text.insert(tk.END, json.dumps(positions, indent=2, ensure_ascii=False))

                    self.log("포지션 조회 완료")
                else:
                    self.position_text.insert(tk.END, "포지션 없음\n")
                    self.log("포지션 없음")
                    self.current_positions = []
            else:
                self.position_text.insert(tk.END, f"오류: {data.get('message')}\n")
                self.log(f"포지션 조회 실패: {data.get('message')}")
        except Exception as e:
            self.position_text.insert(tk.END, f"오류: {str(e)}\n")
            self.log(f"오류: {str(e)}")

    def get_price(self):
        symbol = self.symbol_entry.get().strip().upper()
        if not symbol:
            messagebox.showwarning("경고", "심볼을 입력해주세요.")
            return

        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        try:
            self.log(f"{symbol} 가격 조회 중...")
            url = f"{self.price_url}/{symbol}/USDT"
            response = requests.get(url, headers=headers, impersonate="chrome120")

            data = response.json()

            if data.get("code") == 0:
                price = data["data"]["price"]
                self.current_price_label.config(text=f"현재가: ${price:,.2f}")
                self.log(f"{symbol} 현재가: ${price:,.2f}")
            else:
                self.log(f"가격 조회 실패: {data.get('message')}")
        except Exception as e:
            self.log(f"오류: {str(e)}")

    def place_market_order(self):
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        symbol = self.symbol_entry.get().strip().upper()
        direction = self.direction_var.get()

        try:
            quantity_usd = float(self.quantity_entry.get())
            leverage = int(self.leverage_entry.get())
        except ValueError:
            messagebox.showerror("오류", "수량과 레버리지는 숫자여야 합니다.")
            return

        if not symbol or quantity_usd <= 0:
            messagebox.showerror("오류", "올바른 값을 입력해주세요.")
            return

        confirm = messagebox.askyesno(
            "주문 확인",
            f"{symbol} {direction.upper()} 마켓 주문\n"
            f"금액: ${quantity_usd}\n"
            f"레버리지: {leverage}x\n\n"
            f"주문하시겠습니까?"
        )

        if not confirm:
            return

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        payload = {
            "direction": direction,
            "price": -1,
            "quantity": quantity_usd,
            "leverage_type": "cross",
            "base_asset_id": symbol,
            "initial_margin": quantity_usd * 0.9999,
            "leverage": leverage,
            "initial_margin_asset_id": "USD",
            "order_type": "MarketOpen",
            "expiration_date": -1,
            "is_mobile": False
        }

        try:
            self.log(f"주문 실행 중: {symbol} {direction} ${quantity_usd}")
            response = requests.post(self.order_url, json=payload, headers=headers, impersonate="chrome120")

            data = response.json()

            if data.get("code") == 0:
                order_data = data["data"]
                order_id = order_data.get("id", "unknown")

                self.log(f"주문 성공! ID: {order_id}")
                messagebox.showinfo("성공", f"주문이 접수되었습니다!\n주문 ID: {order_id}")

                self.get_balance()
                self.get_positions()
                self.get_open_orders()
            else:
                error_msg = data.get("message", "알 수 없는 오류")
                self.log(f"주문 실패: {error_msg}")
                messagebox.showerror("주문 실패", error_msg)
        except Exception as e:
            self.log(f"오류: {str(e)}")
            messagebox.showerror("오류", str(e))

    def get_open_orders(self):
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        try:
            self.log("오픈 오더 조회 중...")
            url = f"{self.order_url}?status=open&page=1&pageSize=100"
            response = requests.get(url, headers=headers, impersonate="chrome120")

            data = response.json()
            self.orders_text.delete(1.0, tk.END)

            if data.get("code") == 0:
                orders = data.get("data", {}).get("orders", [])

                if orders:
                    self.orders_text.insert(tk.END, f"총 {len(orders)}개의 오픈 오더\n")
                    self.orders_text.insert(tk.END, f"{'-'*80}\n")

                    for order in orders:
                        order_id = order.get("id", "")[:20]
                        symbol = order.get("base_asset_id", "")
                        direction = order.get("direction", "")
                        quantity = order.get("quantity", 0)
                        price = order.get("price", 0)

                        self.orders_text.insert(tk.END, f"ID: {order_id}...\n")
                        self.orders_text.insert(tk.END, f"{symbol} {direction.upper()} | 수량: {quantity} | 가격: {price}\n")
                        self.orders_text.insert(tk.END, f"{'-'*80}\n")

                    self.log(f"오픈 오더 {len(orders)}개 조회 완료")
                else:
                    self.orders_text.insert(tk.END, "오픈 오더 없음\n")
                    self.log("오픈 오더 없음")
            else:
                self.orders_text.insert(tk.END, f"오류: {data.get('message')}\n")
                self.log(f"오픈 오더 조회 실패: {data.get('message')}")
        except Exception as e:
            self.orders_text.insert(tk.END, f"오류: {str(e)}\n")
            self.log(f"오류: {str(e)}")

    def liquidate_all_positions(self):
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        if not self.current_positions:
            messagebox.showinfo("안내", "청산할 포지션이 없습니다.\n먼저 '포지션 새로고침'을 클릭하세요.")
            return

        confirm = messagebox.askyesno(
            "포지션 청산 확인",
            f"총 {len(self.current_positions)}개의 포지션을 청산하시겠습니까?\n\n"
            f"⚠️ 이 작업은 되돌릴 수 없습니다!"
        )

        if not confirm:
            return

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        success_count = 0
        fail_count = 0

        for position in self.current_positions:
            try:
                position_id = position.get("position_id")
                leverage_id = position.get("leverage_id")
                token_id = position.get("token_id", "")
                amount = position.get("amount", 0)

                if token_id:
                    base_asset_id = token_id
                else:
                    base_asset_id = position.get("base_asset_id", "ETH")

                if not position_id or amount == 0:
                    continue

                try:
                    price_url = f"{self.price_url}/{base_asset_id}/USDT"
                    price_response = requests.get(price_url, headers=headers, impersonate="chrome120")
                    price_data = price_response.json()
                    current_price = price_data["data"]["price"]
                except:
                    current_price = position.get("mark_price", 0)

                payload = {
                    "position_id": position_id,
                    "leverage_id": leverage_id,
                    "price": current_price,
                    "quantity": abs(amount),
                    "base_asset_id": base_asset_id,
                    "order_type": "MarketClose"
                }

                response = requests.post(self.liquidate_url, json=payload, headers=headers, impersonate="chrome120")
                data = response.json()

                if data.get("code") == 0:
                    success_count += 1
                    self.log(f"✓ {base_asset_id} 포지션 청산 성공")
                else:
                    fail_count += 1
                    self.log(f"✗ {base_asset_id} 포지션 청산 실패: {data.get('message')}")

            except Exception as e:
                fail_count += 1
                self.log(f"✗ 포지션 청산 오류: {str(e)}")

        result_msg = f"청산 완료!\n\n성공: {success_count}개\n실패: {fail_count}개"
        if success_count > 0:
            messagebox.showinfo("청산 완료", result_msg)
        else:
            messagebox.showwarning("청산 실패", result_msg)

        if success_count > 0:
            self.get_balance()
            self.get_positions()
            self.get_open_orders()

    def quick_liquidate(self):
        """자동 거래 중 즉시 청산"""
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        confirm = messagebox.askyesno(
            "즉시 청산 확인",
            "모든 포지션을 즉시 청산하시겠습니까?\n\n"
            "⚠️ 자동 거래가 진행 중이어도 청산됩니다!"
        )

        if not confirm:
            return

        self.auto_log("⚡ 즉시 청산 시작...")
        success = self.liquidate_auto()

        if success:
            self.auto_log("✓ 즉시 청산 완료!")
            messagebox.showinfo("완료", "포지션이 청산되었습니다.")
        else:
            self.auto_log("✗ 즉시 청산 실패")
            messagebox.showwarning("실패", "청산할 포지션이 없거나 실패했습니다.")

    def start_auto_trading(self):
        if not self.access_token:
            messagebox.showwarning("경고", "먼저 로그인해주세요.")
            return

        try:
            repeat_count = int(self.repeat_count_entry.get())
            wait_time = int(self.wait_time_entry.get())
            quantity_usd = float(self.auto_quantity_entry.get())
            leverage = int(self.auto_leverage_entry.get())
        except ValueError:
            messagebox.showerror("오류", "반복 횟수, 대기 시간, 수량, 레버리지는 숫자여야 합니다.")
            return

        symbol = self.auto_symbol_entry.get().strip().upper()
        direction = self.auto_direction_var.get()

        if not symbol or repeat_count <= 0 or wait_time <= 0 or quantity_usd <= 0:
            messagebox.showerror("오류", "올바른 값을 입력해주세요.")
            return

        confirm = messagebox.askyesno(
            "자동 거래 시작 확인",
            f"다음 설정으로 자동 거래를 시작하시겠습니까?\n\n"
            f"심볼: {symbol}\n"
            f"방향: {direction.upper()}\n"
            f"수량: ${quantity_usd}\n"
            f"레버리지: {leverage}x\n"
            f"반복 횟수: {repeat_count}회\n"
            f"대기 시간: {wait_time}초\n\n"
            f"총 예상 소요 시간: {(wait_time * repeat_count) // 60}분"
        )

        if not confirm:
            return

        self.auto_trading = True
        self.start_auto_btn.config(state=tk.DISABLED)
        self.stop_auto_btn.config(state=tk.NORMAL)

        self.auto_thread = threading.Thread(
            target=self.auto_trading_loop,
            args=(repeat_count, wait_time, symbol, direction, quantity_usd, leverage),
            daemon=True
        )
        self.auto_thread.start()

    def stop_auto_trading(self):
        self.auto_trading = False
        self.auto_status_label.config(text="중지 중...", foreground="orange")
        self.auto_log("자동 거래 중지 요청됨")

    def auto_trading_loop(self, repeat_count, wait_time, symbol, direction, quantity_usd, leverage):
        try:
            for i in range(repeat_count):
                if not self.auto_trading:
                    self.auto_log("자동 거래 중지됨")
                    break

                current_round = i + 1
                self.auto_status_label.config(text=f"진행 중: {current_round}/{repeat_count}", foreground="green")
                self.auto_log(f"\n{'='*50}")
                self.auto_log(f"라운드 {current_round}/{repeat_count} 시작")
                self.auto_log(f"{'='*50}")

                # 1. 주문 넣기
                self.auto_log(f"1단계: {symbol} {direction} 주문 실행 중...")
                success = self.place_auto_order(symbol, direction, quantity_usd, leverage)

                if not success:
                    self.auto_log("⚠️ 주문 실패! 다음 라운드로...")
                    time.sleep(5)
                    continue

                self.auto_log("✓ 주문 성공!")

                # 1-2. 포지션 생성 확인 (3초 대기 후)
                time.sleep(3)
                self.auto_log("1-2단계: 포지션 생성 확인 중...")

                headers = {
                    "accept": "application/json",
                    "authorization": f"Bearer {self.access_token}",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "origin": "https://app.vdex.trade",
                    "referer": "https://app.vdex.trade/"
                }

                try:
                    response = requests.get(self.positions_url, headers=headers, impersonate="chrome120")
                    data = response.json()

                    if data.get("code") == 0:
                        positions = data.get("data", [])
                        if positions:
                            self.auto_log(f"✓ 포지션 확인됨: {len(positions)}개")
                        else:
                            self.auto_log("⚠️ 포지션이 아직 생성되지 않았습니다")
                    else:
                        self.auto_log("⚠️ 포지션 조회 실패")
                except Exception as e:
                    self.auto_log(f"⚠️ 포지션 확인 오류: {str(e)}")

                # 2. 대기
                self.auto_log(f"2단계: {wait_time}초 대기 중...")
                for sec in range(wait_time):
                    if not self.auto_trading:
                        self.auto_log("자동 거래 중지됨")
                        return

                    remaining = wait_time - sec
                    self.auto_status_label.config(
                        text=f"대기 중: {current_round}/{repeat_count} ({remaining}초 남음)",
                        foreground="blue"
                    )
                    time.sleep(1)

                # 3. 포지션 청산
                self.auto_log(f"3단계: 포지션 청산 중...")
                liquidate_success = self.liquidate_auto()

                if liquidate_success:
                    self.auto_log("✓ 청산 성공!")
                else:
                    self.auto_log("⚠️ 청산 실패! 계속 진행...")

                self.auto_log(f"라운드 {current_round} 완료\n")

                # 마지막 라운드가 아니면 잠시 대기
                if current_round < repeat_count and self.auto_trading:
                    time.sleep(2)

            # 완료
            if self.auto_trading:
                self.auto_status_label.config(text=f"완료: {repeat_count}회 실행됨", foreground="green")
                self.auto_log(f"\n{'='*50}")
                self.auto_log(f"자동 거래 완료! 총 {repeat_count}회 실행됨")
                self.auto_log(f"{'='*50}")
                messagebox.showinfo("완료", f"자동 거래가 완료되었습니다!\n총 {repeat_count}회 실행됨")

        except Exception as e:
            self.auto_log(f"오류 발생: {str(e)}")
            messagebox.showerror("오류", f"자동 거래 중 오류 발생:\n{str(e)}")
        finally:
            self.auto_trading = False
            self.start_auto_btn.config(state=tk.NORMAL)
            self.stop_auto_btn.config(state=tk.DISABLED)
            if not self.auto_trading:
                self.auto_status_label.config(text="대기 중", foreground="gray")

    def place_auto_order(self, symbol, direction, quantity_usd, leverage):
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        payload = {
            "direction": direction,
            "price": -1,
            "quantity": quantity_usd,
            "leverage_type": "cross",
            "base_asset_id": symbol,
            "initial_margin": quantity_usd * 0.9999,
            "leverage": leverage,
            "initial_margin_asset_id": "USD",
            "order_type": "MarketOpen",
            "expiration_date": -1,
            "is_mobile": False
        }

        try:
            response = requests.post(self.order_url, json=payload, headers=headers, impersonate="chrome120")
            data = response.json()

            if data.get("code") == 0:
                order_id = data["data"].get("id", "unknown")
                self.auto_log(f"  주문 ID: {order_id}")
                return True
            else:
                error_msg = data.get("message", "알 수 없는 오류")
                self.auto_log(f"  주문 실패: {error_msg}")
                return False
        except Exception as e:
            self.auto_log(f"  주문 오류: {str(e)}")
            return False

    def liquidate_auto(self):
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "origin": "https://app.vdex.trade",
            "referer": "https://app.vdex.trade/"
        }

        try:
            response = requests.get(self.positions_url, headers=headers, impersonate="chrome120")
            data = response.json()

            if data.get("code") != 0:
                self.auto_log("  포지션 조회 실패")
                return False

            positions = data.get("data", [])
            if not positions:
                self.auto_log("  청산할 포지션 없음")
                return True

            success_count = 0

            for position in positions:
                position_id = position.get("position_id")
                leverage_id = position.get("leverage_id")
                token_id = position.get("token_id", "")
                amount = position.get("amount", 0)

                if not token_id:
                    token_id = position.get("base_asset_id", "ETH")

                if not position_id or amount == 0:
                    continue

                try:
                    price_url = f"{self.price_url}/{token_id}/USDT"
                    price_response = requests.get(price_url, headers=headers, impersonate="chrome120")
                    price_data = price_response.json()
                    current_price = price_data["data"]["price"]
                except:
                    current_price = position.get("mark_price", 0)

                payload = {
                    "position_id": position_id,
                    "leverage_id": leverage_id,
                    "price": current_price,
                    "quantity": abs(amount),
                    "base_asset_id": token_id,
                    "order_type": "MarketClose"
                }

                response = requests.post(self.liquidate_url, json=payload, headers=headers, impersonate="chrome120")
                data = response.json()

                if data.get("code") == 0:
                    success_count += 1
                    self.auto_log(f"  ✓ {token_id} 포지션 청산 성공")

            return success_count > 0

        except Exception as e:
            self.auto_log(f"  청산 오류: {str(e)}")
            return False

def main():
    root = tk.Tk()
    app = VDEXTrader(root)
    root.mainloop()

if __name__ == "__main__":
    main()
