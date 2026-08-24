const database = db.getSiblingDB("open5gs");
const imsi = "999700000000001";

if (!database.subscribers.findOne({imsi: imsi})) {
  database.subscribers.insertOne({
    schema_version: NumberInt(1),
    imsi: imsi,
    msisdn: [],
    imeisv: [],
    mme_host: [],
    mm_realm: [],
    purge_flag: [],
    slice: [{
      sst: NumberInt(1),
      default_indicator: true,
      session: [{
        name: "internet",
        type: NumberInt(1),
        qos: {
          index: NumberInt(9),
          arp: {
            priority_level: NumberInt(8),
            pre_emption_capability: NumberInt(1),
            pre_emption_vulnerability: NumberInt(2)
          }
        },
        ambr: {
          downlink: {value: NumberInt(1000000000), unit: NumberInt(0)},
          uplink: {value: NumberInt(1000000000), unit: NumberInt(0)}
        },
        pcc_rule: []
      }]
    }],
    security: {
      k: "465B5CE8B199B49FAA5F0A2EE238A6BC",
      op: null,
      opc: "E8ED289DEBA952E4283B54E88E6183CA",
      amf: "8000"
    },
    ambr: {
      downlink: {value: NumberInt(1000000000), unit: NumberInt(0)},
      uplink: {value: NumberInt(1000000000), unit: NumberInt(0)}
    },
    access_restriction_data: NumberInt(32),
    network_access_mode: NumberInt(0),
    subscriber_status: NumberInt(0),
    operator_determined_barring: NumberInt(0),
    subscribed_rau_tau_timer: NumberInt(12),
    __v: NumberInt(0)
  });
}
