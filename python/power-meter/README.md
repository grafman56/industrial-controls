# Power meter

A three-phase feeder meter that answers Modbus/TCP, with the register map as
data in `registers.json`. Standard library only.

This is what an EPMS or a BMS polls. The point is not electrical simulation. The
point is that everything between 26 raw registers and the number on a dashboard
is in this directory, and you can read all of it.

## The map

`registers.json` holds one entry per measurement: register address, type, word
order, scale, and unit. The meter builds its register image from that file, and
the example poller decodes with the same file. Move an address in the JSON and
both sides follow.

Two entries show the traps, on purpose:

- `energy_import` is a `uint32` sent **low word first**, scaled by 0.1. Read it
  as high word first and you get a plausible kWh figure that is wrong by a
  factor of 65536.
- `voltage_l1_n` is a `float32` across two registers. Read it as an integer and
  you get 17254, which looks like a raw count and is not.

The map covers 26 registers, and the last one, `register_count`, says so. A
poller can read that register first and size its next read from it.

## Run it

```bash
python3 python/power-meter/meter.py --print
```

That prints every register, its raw words, and its decoded value:

```
  voltage_l1_n            0 float32  high_first raw=[17254, 0] value=230 V
  energy_import          20 uint32   low_first  raw=[57920, 1] value=12345.6 kWh
```

Then serve it and read it back over TCP:

```bash
python3 python/power-meter/meter.py --port 15020 --scenario phase-loss
python3 python/power-meter/read_meter.py --port 15020
```

The reader is a real Modbus/TCP client: it builds a function 3 request, checks
the transaction id and the length, and decodes the response with the map.

## Scenarios

| Scenario | What changes |
|---|---|
| `balanced` | 230 V per line, 120 A, 77.8 kW, power factor 0.94 |
| `phase-loss` | Line 2 at 0 V, lines 1 and 3 at 115 percent current, power down, total harmonic distortion up |
| `overload` | 168 A per line, 109 kW, distortion up |

Phase loss is the drill. Start the meter in `phase-loss`, poll it with any
client, and answer three questions before you look at the code: what does the
meter report, what does a naive dashboard show, and what would an electrician
notice that the dashboard does not.

## Prove it

```bash
python3 -m unittest tests.test_power_meter
```

Seventeen tests. The ones worth reading:

- `test_reading_low_word_first_data_as_high_word_first_gives_a_wrong_number`
- `test_a_signed_reading_of_a_float32_register_pair_is_wrong`
- `test_a_read_past_the_end_is_an_exception_two`
- `test_the_example_poller_reads_the_whole_map`

## Use it in the lab

The `modbus-tcp` lab uses port 5020 and its own tank model. This meter is a
separate process on a separate port, so it can run beside that lab. Point the
`scada-hmi` poller at it by registering the host and port, and the Grafana
dashboard reads a meter instead of a tank.

## What it does not do

- No current transformer ratio, so the current registers are primary amps.
- No harmonics beyond one total distortion register per line.
- No event log, no waveform capture, no time synchronisation.
- No Modbus write. It reports; it does not accept a breaker command.

Each of those is a real meter feature and a good next exercise. Waveform
capture is the one worth doing first, because it is what separates a meter from
a power quality analyser.
