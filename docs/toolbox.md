# Toolbox

What to install, what each tool proves, and the order to install it in. Nothing
here needs a licence, and nothing here needs a vendor account.

## The laptop

| Tool | What it does | What it proves |
|---|---|---|
| OpenPLC Editor | Writes and compiles IEC 61131-3 programs, exports PLCopen XML | You can produce a program, not only read one |
| Wireshark | Captures and dissects Modbus/TCP, BACnet/IP, SNMP | You can say what is on the wire, with a frame number |
| Python 3 | Runs `python/`, `tools/plcopen.py`, and any scripted client | You can turn a manual into a tool |
| A terminal | Containerlab, SSH, Modbus clients | You can operate the thing you built |

Install in that order. The editor first, because a program that will not compile
teaches more in an hour than a protocol class does in a week.

## The lab host

| Tool | What it does | Where it is used here |
|---|---|---|
| Containerlab | Starts a topology from one YAML file | `labs.toml`, `./labctl` |
| OpenPLC Runtime | Executes a compiled program on a real scan cycle | `modbus-tcp`, `scada-hmi` |
| FUXA | Browser HMI with a Modbus driver | `scada-hmi` |
| InfluxDB | Time-series store for process values | `scada-hmi` |
| Grafana | Dashboards and alert rules | `scada-hmi` |

## Optional, and worth it later

| Tool | Why |
|---|---|
| `pymodbus` | The common Python Modbus library. Read it to compare with the standard-library frames in `python/power-meter/`, then use it for real work |
| Node-RED | Common glue in building management and small SCADA. Good for a quick bridge between a protocol and a dashboard |
| Zeek | Turns a capture into a connection log. This is the tool that shows what a plant network does at three in the morning |
| Modbus client GUI | Fast manual reads while you learn. Any client works. Do not let it become the only way you read a meter |

## What to skip for now

- A SCADA platform with a licence. The concepts are the same and FUXA covers
  them for learning.
- A historian with a cluster. One InfluxDB bucket on one container is enough to
  learn retention, downsampling, and query shape.
- Protocol converters you do not need. Every gateway you add hides a protocol
  you have not learned yet.

## The one hardware purchase

The gap no container closes is electrical. A suitable first purchase is a
Raspberry Pi running OpenPLC Runtime, a 24 V supply, and a relay board with
screw terminals.

That gives you the three things software cannot:

1. A real 24 V loop, with the wiring faults you already know how to find.
2. A real output that switches a load, with contact wear and inrush current.
3. A real scan time, which you can measure with a timer instruction and a
   stopwatch.

Wire the relay to a lamp first. Then wire an emergency stop in series with the
supply, and prove that opening it stops the output even when the program says
run. That test is the reason the interlock exists in every program in `plc/`.

## Reading a capture

The first capture worth taking is one Modbus read of the meter in
`python/power-meter/`:

1. Start the meter on loopback.
2. Start a capture on the loopback interface, filtered to the port.
3. Run `python/power-meter/read_meter.py`.
4. Stop the capture and open it.

You will see a request with a transaction id and a function code, and a reply
with a byte count and the register words. Compare those words with
`meter.py --print`. When the words and the printed value agree, you can read a
register map from a manual without help.
