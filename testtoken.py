import os
import hashlib
import platform
from typing import Dict

from ipyeos import eos
from ipyeos import chaintester
from ipyeos.chaintester import ChainTester
from ipyeos import log

chaintester.chain_config['contracts_console'] = True
eos.set_log_level("default", 3)

logger = log.get_logger(__name__)

dir_name = os.path.dirname(os.path.abspath(__file__))

def update_auth(chain, account):
    a = {
        "account": account,
        "permission": "active",
        "parent": "owner",
        "auth": {
            "threshold": 1,
            "keys": [
                {
                    "key": 'EOS6AjF6hvF7GSuSd4sCgfPKq5uWaXvGM2aQtEUCwmEHygQaqxBSV',
                    "weight": 1
                }
            ],
            "accounts": [{"permission":{"actor":account,"permission": 'eosio.code'}, "weight":1}],
            "waits": []
        }
    }
    chain.push_action('eosio', 'updateauth', a, {account:'active'})

def init_test():
    t = ChainTester(True)
    update_auth(t, 'hello')
    wasm_file = os.path.join(dir_name, '../../build/test/wasm/token.wasm')
    with open(wasm_file, 'rb') as f:
        code = f.read()

    abi_file = os.path.join(dir_name, '../../build/test/wasm/token.abi')
    with open(abi_file, 'r') as f:
        abi = f.read()

    t.deploy_contract('hello', code, abi)
    t.produce_block()
    eos.set_log_level("default", 1)

    eos.enable_debug(True)
    native_lib = os.path.join(dir_name, '../../build/test/wasm/libtestmi.so')
    native_lib = os.path.abspath(native_lib)
    # t.chain.set_native_contract('hello', native_lib)

    return t

# print('pid:', os.getpid())
# input("Press Enter to continue...")

def push_action_require_exception(t, contract: str, action: str, args: Dict, permission: Dict, exception_message: str):
    try:
        t.push_action(contract, action, args, permission)
        t.produce_block()
        assert False, "should not go here!"
    except Exception as e:
        e = e.args[0]
        assert e['action_traces'][0]['except']['stack'][0]['data']['s'] == exception_message

def test_create():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1000.000 TKN",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "0.000 TKN"
    assert ret['rows'][0]['max_supply'] == "1000.000 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

def test_create_negative_max_supply():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "-1000.000 TKN",
    }
    push_action_require_exception(t, "hello", "create", args, {"alice": "active"}, "max_supply must be positive")

def test_symbol_already_exists():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "100 TKN",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()
    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "0 TKN"
    assert ret['rows'][0]['max_supply'] == "100 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

    push_action_require_exception(t, "hello", "create", args, {"alice": "active"}, "token with symbol already exists")

def test_create_max_supply():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "4611686018427387903 TKN",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()
    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "0 TKN"
    assert ret['rows'][0]['max_supply'] == "4611686018427387903 TKN"
    assert ret['rows'][0]['issuer'] == "alice"


    args = {
        "issuer": "alice",
        "maximum_supply": "4611686018427387903 TKN",
    }
    args = t.pack_action_args('hello', 'create', args)
    logger.info(args)
    args = args[:8] + int.to_bytes(4611686018427387904, 8, 'little') + args[16:]
    push_action_require_exception(t, "hello", "create", args, {"alice": "active"}, "magnitude of asset amount must be less than 2^62")

def test_create_max_decimals():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1.000000000000000000 TKN",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()
    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "0.000000000000000000 TKN"
    assert ret['rows'][0]['max_supply'] == "1.000000000000000000 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

    args = {
        "issuer": "alice",
        "maximum_supply": "1.000000000000000000 TKN",
    }
    args = t.pack_action_args('hello', 'create', args)
    #1.000000000000000000 TKN
#    1.0000000000000000000 => 0x8ac7230489e80000L
    amount = 0x8ac7230489e80000
    args = args[:8] + int.to_bytes(amount, 8, 'little') + args[16:]
    push_action_require_exception(t, "hello", "create", args, {"alice": "active"}, "magnitude of asset amount must be less than 2^62")

def test_issue_tests():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1000.000 TKN",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()

    args = {
        "to": "alice",
        "quantity": "500.000 TKN",
        "memo": "hola"
    }
    t.push_action("hello", "issue", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "500.000 TKN"
    assert ret['rows'][0]['max_supply'] == "1000.000 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

def test_retire_tests():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1000.000 TKN",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()

    args = {
        "to": "alice",
        "quantity": "500.000 TKN",
        "memo": "hola"
    }
    t.push_action("hello", "issue", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "500.000 TKN"
    assert ret['rows'][0]['max_supply'] == "1000.000 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '500.000 TKN'

    args = {
        "quantity": "200.000 TKN",
        "memo": "hola"
    }
    t.push_action("hello", "retire", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "300.000 TKN"
    assert ret['rows'][0]['max_supply'] == "1000.000 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '300.000 TKN'

    args = {
        "quantity": "500.000 TKN",
        "memo": "hola"
    }
    push_action_require_exception(t, "hello", "retire", args, {"alice": 'active'}, "overdrawn balance")

    args = {
        "from": "alice",
        "to": "bob",
        "quantity": "200.000 TKN",
        "memo":  "hola"
    }
    t.push_action("hello", 'transfer', args, {"alice": 'active'})
    t.produce_block()
#   should fail to retire since tokens are not on the issuer's balance
    args = {
        "quantity": "300.000 TKN",
        "memo": "hola"
    }
    push_action_require_exception(t, "hello", "retire", args, {"alice": 'active'}, "overdrawn balance")

#   transfer tokens back
    args = {
        "from": "bob",
        "to": "alice",
        "quantity": "200.000 TKN",
        "memo":  "hola"
    }
    t.push_action("hello", 'transfer', args, {"bob": 'active'})
    t.produce_block()

    args = {
        "quantity": "300.000 TKN",
        "memo": "hola"
    }
    t.push_action("hello", "retire", args, {"alice": 'active'})

    ret = t.get_table_rows(True, "hello", "TKN", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "0.000 TKN"
    assert ret['rows'][0]['max_supply'] == "1000.000 TKN"
    assert ret['rows'][0]['issuer'] == "alice"

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '0.000 TKN'

#   trying to retire tokens with zero supply
    args = {
        "quantity": "1.000 TKN",
        "memo": "hola"
    }
    push_action_require_exception(t, "hello", "retire", args, {"alice": 'active'}, "overdrawn balance")

def test_transfer_tests():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1000 CERO",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()

    args = {
        "to": "alice",
        "quantity": "1000 CERO",
        "memo": "hola"
    }
    t.push_action("hello", "issue", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "CERO", "stat", '', '', 10)
    logger.info(ret)
    assert ret['rows'][0]['supply'] == "1000 CERO"
    assert ret['rows'][0]['max_supply'] == "1000 CERO"
    assert ret['rows'][0]['issuer'] == "alice"

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '1000 CERO'
    args = {
        'from': 'alice',
        'to': 'bob',
        'quantity': '300 CERO',
        'memo': 'hola'
    }
    t.push_action('hello', 'transfer', args, {'alice': 'active'})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "alice", "accounts", 'CERO', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '700 CERO'

    ret = t.get_table_rows(True, "hello", "bob", "accounts", 'CERO', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '300 CERO'

    try:
        args = {
            'from': 'alice',
            'to': 'bob',
            'quantity': '701 CERO',
            'memo': 'hola'
        }
        t.push_action("hello", "transfer", args, {"alice": "active"})
        t.produce_block()
        assert False, "should not go here!"
    except Exception as e:
        e = e.args[0]
        assert e['action_traces'][0]['except']['stack'][0]['data']['s'] == 'overdrawn balance'

    try:
        args = {
            'from': 'alice',
            'to': 'bob',
            'quantity': '-1000 CERO',
            'memo': 'hola'
        }
        t.push_action("hello", "transfer", args, {"alice": "active"})
        t.produce_block()
        assert False, "should not go here!"
    except Exception as e:
        e = e.args[0]
        assert e['action_traces'][0]['except']['stack'][0]['data']['s'] == 'must transfer positive quantity'

def test_open_tests():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1000 CERO",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "bob", "accounts", 'CERO', '', 10)
    logger.info(ret)
    assert not ret['rows']

    args = {
        "to": "bob",
        "quantity": "1000 CERO",
        "memo": "hola"
    }
    push_action_require_exception(t, "hello", "issue", args, {"alice": 'active'}, "tokens can only be issued to issuer account")

    args = {
        "to": "alice",
        "quantity": "1000 CERO",
        "memo": "hola"
    }
    t.push_action("hello", "issue", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '1000 CERO'

    ret = t.get_table_rows(True, "hello", "bob", "accounts", '', '', 10)
    assert not ret['rows']

    args = {
        "owner": "nonexistent",
        "symbol": "0,CERO",
        "ram_payer": "alice"
    }
    push_action_require_exception(t, "hello", "open", args, {"alice": 'active'}, "owner account does not exist")

    args = {
        "owner": "bob",
        "symbol": "0,CERO",
        "ram_payer": "alice"
    }
    t.push_action("hello", "open", args, {"alice": 'active'})

    ret = t.get_table_rows(True, "hello", "bob", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '0 CERO'

    args = {
        "from": "alice",
        "to": "bob",
        "quantity": "200 CERO",
        "memo": 'hola'
    }
    t.push_action("hello", "transfer", args, {"alice": 'active'})

    ret = t.get_table_rows(True, "hello", "bob", "accounts", '', '', 10)
    balance = ret['rows'][0]['balance']
    assert balance == '200 CERO'

    args = {
        "owner": "testmetestme",
        "symbol": "0,INVALID",
        "ram_payer": "alice"
    }
    push_action_require_exception(t, "hello", "open", args, {"alice": 'active'}, "symbol does not exist")

    args = {
        "owner": "testmetestme",
        "symbol": "1,CERO",
        "ram_payer": "alice"
    }
    push_action_require_exception(t, "hello", "open", args, {"alice": 'active'}, "symbol precision mismatch")

def test_close():
    t = init_test()
    args = {
        "issuer": "alice",
        "maximum_supply": "1000 CERO",
    }
    t.push_action("hello", "create", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    assert not ret['rows']

    args = {
        "to": "alice",
        "quantity": "1000 CERO",
        "memo": "hola"
    }
    t.push_action("hello", "issue", args, {"alice": "active"})
    t.produce_block()

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    assert ret['rows'][0]['balance'] == "1000 CERO"
    args = {
        'from': 'alice',
        'to': 'bob',
        'quantity': '1000 CERO',
        'memo': 'hola'
    }
    t.push_action("hello", "transfer", args, {"alice": "active"})
    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    assert ret['rows'][0]['balance'] == "0 CERO"

    args = {
        'owner': 'alice',
        'symbol': '0,CERO',
    }
    t.push_action("hello", "close", args, {"alice": "active"})

    ret = t.get_table_rows(True, "hello", "alice", "accounts", '', '', 10)
    assert not ret['rows']
